"""POS (PDV) — point of sale view for counter operations."""

from __future__ import annotations

import json
import logging

from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.urls import reverse
from django.utils.html import escape, format_html
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST
from shopman.utils.monetary import format_money

from shopman.backstage.constants import POS_CHANNEL_REF
from shopman.backstage.projections.pos import build_pos, build_pos_shift_summary, build_pos_tabs
from shopman.backstage.services import pos as pos_cash_service
from shopman.backstage.services.exceptions import POSError
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import PosIntentError

logger = logging.getLogger(__name__)


PERM = "backstage.operate_pos"


def _pos_error_response(exc: PosIntentError, *, fallback_status: int = 422) -> HttpResponse:
    """Render a POS validation error with stable recovery metadata."""
    status = getattr(exc, "status", None) or fallback_status
    recovery = exc.recovery or "Corrija os dados destacados e tente novamente."
    return HttpResponse(
        '<div class="px-3 py-2 rounded-lg bg-danger/10 border border-danger/30 text-danger text-sm" '
        f'data-error-code="{escape(exc.code)}" '
        f'data-focus-target="{escape(exc.focus)}" '
        f'data-error-field="{escape(exc.field)}">'
        f'<span class="font-semibold">{escape(exc.message)}</span>'
        f'<br><span class="text-xs text-on-surface/50 dark:text-on-surface-dark/50">{escape(recovery)}</span>'
        '</div>',
        status=status,
    )


def _perm_required(request):
    """Redirect to login if not staff; 403 if missing operate_pos perm."""
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect(f"/admin/login/?next={request.path}")
    if not request.user.has_perm(PERM):
        return HttpResponseForbidden("Você não tem permissão para esta ação.")
    return None


# ── Views ───────────────────────────────────────────────────────────


@require_GET
def pos_view(request: HttpRequest) -> HttpResponse:
    """GET /gestor/pos/ — main POS page."""
    denied = _perm_required(request)
    if denied:
        return denied

    from shopman.backstage.models import CashShift
    from shopman.shop.models import Shop

    shop = Shop.load()
    cash_session = CashShift.get_open_for_operator(request.user)

    if not cash_session:
        return render(request, "pos/cash_open.html", {"shop": shop})

    pos = build_pos(terminal=cash_session.terminal)

    return render(request, "pos/index.html", {
        "pos": pos,
        "products": pos.products,
        "collections": pos.collections,
        "shop": shop,
        "payment_methods": pos.payment_methods,
        "cash_session": cash_session,
        "terminal_profile": pos,
    })


@require_POST
def pos_customer_lookup(request: HttpRequest) -> HttpResponse:
    """POST /gestor/pos/customer-lookup/ — HTMX: return customer name partial."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse("", status=403)

    phone = request.POST.get("phone", "").strip()
    if not phone:
        return HttpResponse('<span class="text-muted-foreground">Cliente avulso</span>')

    try:
        customer = pos_service.resolve_customer(phone)
        if customer:
            name = f"{customer.first_name} {customer.last_name}".strip()
            group_ref = customer.group.ref if customer.group_id else ""
            summary = pos_service.customer_history_summary(customer.ref)
            default_address = customer.default_address
            bits = []
            if summary.get("total_orders"):
                bits.append(f'{summary["total_orders"]} pedidos')
            if summary.get("average_order_q"):
                bits.append(f'ticket médio R$ {format_money(summary["average_order_q"])}')
            if summary.get("favorite_product"):
                bits.append(f'prefere {summary["favorite_product"]}')
            memory = " · ".join(bits) if bits else "sem histórico ainda"
            favorite_item = json.dumps(summary.get("favorite_item") or {}, ensure_ascii=False)
            last_order_items = json.dumps(summary.get("last_order_items") or [], ensure_ascii=False)
            staff_badge = " (staff)" if group_ref == "staff" else ""
            return HttpResponse(
                format_html(
                    '<span class="text-primary font-semibold" '
                    'data-customer-name="{}" '
                    'data-customer-ref="{}" '
                    'data-customer-group="{}" '
                    'data-customer-email="{}" '
                    'data-default-address="{}" '
                    'data-favorite-item="{}" '
                    'data-last-order-items="{}">'
                    '{}{}'
                    '</span>'
                    '<span class="text-on-surface/50 dark:text-on-surface-dark/50">· {}</span>',
                    name,
                    customer.ref,
                    group_ref,
                    customer.email or "",
                    default_address.formatted_address if default_address else "",
                    favorite_item,
                    last_order_items,
                    name,
                    staff_badge,
                    memory,
                )
            )
    except Exception:
        logger.exception("pos_customer_lookup failed")

    return HttpResponse('<span class="text-muted-foreground">Cliente n&atilde;o encontrado</span>')


@require_POST
def pos_close(request: HttpRequest) -> HttpResponse:
    """POST /gestor/pos/close/ — HTMX: create order, return result partial."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse("Unauthorized", status=403)

    # Parse payload from hx-vals
    payload_str = request.POST.get("payload", "")
    if not payload_str:
        return HttpResponse(
            '<div class="px-3 py-2 rounded-lg bg-danger/10 border border-danger/30 text-danger text-sm font-semibold">'
            'Carrinho vazio — adicione produtos antes de fechar.</div>',
            status=422,
        )

    try:
        body = json.loads(payload_str)
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(
            '<div class="px-3 py-2 rounded-lg bg-danger/10 border border-danger/30 text-danger text-sm font-semibold">'
            'Dados inválidos. Tente novamente.</div>',
            status=400,
        )

    items = body.get("items", [])
    if not items:
        return HttpResponse(
            '<div class="px-3 py-2 rounded-lg bg-danger/10 border border-danger/30 text-danger text-sm font-semibold">'
            'Carrinho vazio — adicione produtos antes de fechar.</div>',
            status=422,
        )

    try:
        from shopman.backstage.models import CashShift

        cash_shift = CashShift.get_open_for_operator(request.user)
        if cash_shift:
            body["cash_shift_id"] = cash_shift.pk
            body["pos_terminal_ref"] = cash_shift.terminal.ref
        result = pos_service.close_sale(
            channel_ref=POS_CHANNEL_REF,
            payload=body,
            actor=f"pos:{request.user.username}",
            operator_username=request.user.username,
        )
    except PosIntentError as e:
        logger.info("pos_close_intent_rejected code=%s field=%s user=%s", e.code, e.field, request.user.username)
        return _pos_error_response(e)
    except Exception as e:
        logger.exception("pos_close failed")
        lower = str(e).lower()
        if lower.startswith("canal "):
            return HttpResponse(
                f'<div class="px-3 py-2 rounded-lg bg-danger/10 border border-danger/30 text-danger text-sm font-semibold">'
                f'{e}</div>',
                status=500,
            )
        is_stock_error = (
            "insuficiente" in lower
            or "estoque" in lower
            or "stock" in lower
            or "unavailable" in lower
        )
        return HttpResponse(
            f'<div class="px-3 py-2 rounded-lg bg-danger/10 border border-danger/30 text-danger text-sm">'
            f'<span class="font-semibold">{"Produto indisponível" if is_stock_error else "Erro ao finalizar pedido"}</span> — {e}'
            f'<br><span class="text-xs text-on-surface/50 dark:text-on-surface-dark/50">'
            f'{"Remova o item e tente novamente." if is_stock_error else "Tente novamente ou limpe o carrinho."}'
            f'</span></div>',
            status=422 if is_stock_error else 400,
        )

    total_display = f"R$ {format_money(result.total_q)}"
    order_url = reverse("admin_console_order_detail", args=[result.order_ref])

    # Return HTML partial with data attributes for Alpine to read
    response = HttpResponse(
        f'<div data-order-ref="{result.order_ref}" '
        f'data-total-display="{total_display}" '
        f'data-order-url="{escape(order_url)}" '
        f'class="px-3 py-2 rounded-lg bg-success/10 border border-success/30 text-success text-sm font-semibold flex items-center justify-between gap-2">'
        f'<span>Pedido confirmado e encaminhado{escape(result.fiscal_hint)}</span>'
        f'<span class="flex items-center gap-2">'
        f'<span class="tabular-nums">{result.order_ref} · {total_display}</span>'
        f'<a href="{escape(order_url)}" class="underline underline-offset-2">Gestor</a>'
        f'</span>'
        f'</div>'
    )
    # Trigger shift summary refresh via HTMX event
    response["HX-Trigger"] = "posOrderCreated"
    return response


@require_GET
def pos_shift_summary(request: HttpRequest) -> HttpResponse:
    """GET /gestor/pos/shift-summary/ — HTMX partial: today's shift totals."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse("", status=403)

    summary = build_pos_shift_summary()

    return render(request, "pos/partials/shift_summary.html", {
        "shift_count": summary.count,
        "shift_total_display": summary.total_display,
        "pickup_count": summary.pickup_count,
        "delivery_count": summary.delivery_count,
        "cash_total_display": summary.cash_total_display,
        "digital_total_display": summary.digital_total_display,
        "cod_pending_count": summary.cod_pending_count,
        "cod_pending_display": summary.cod_pending_display,
        "last_ref": summary.last_ref,
        "last_total_display": summary.last_total_display,
    })


@require_POST
def pos_cancel_last(request: HttpRequest) -> HttpResponse:
    """POST /gestor/pos/cancel-last/ — HTMX: cancel the last POS order (within 5 min)."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse("Unauthorized", status=403)

    order_ref = request.POST.get("order_ref", "").strip()
    if not order_ref:
        return HttpResponse(
            '<div id="pos-cancel-result" class="pos-error" '
            'style="background:var(--error-light);color:rgb(var(--error-foreground))">'
            'Refer&ecirc;ncia do pedido n&atilde;o informada</div>',
            status=422,
        )

    try:
        reason = request.POST.get("reason", "").strip()
        if reason:
            pos_service.reopen_recent_order_for_correction(
                order_ref=order_ref,
                actor=f"pos:{request.user.username}",
                reason=reason,
            )
        else:
            pos_service.cancel_recent_order(
                order_ref=order_ref,
                actor=f"pos:{request.user.username}",
            )
    except Exception as e:
        logger.exception("pos_cancel_last failed for order %s", order_ref)
        status = 404 if "não encontrado" in str(e) else 422
        return HttpResponse(
            f'<div id="pos-cancel-result" class="pos-error" '
            f'style="background:var(--error-light);color:rgb(var(--error-foreground))">'
            f'{e}</div>',
            status=status,
        )

    return HttpResponse(
        f'<div id="pos-cancel-result" class="pos-success" '
        f'style="background:var(--success-light,#dcfce7);color:var(--success-foreground,#166534)">'
        f'Venda {order_ref} cancelada com sucesso</div>'
    )


# ── POS Tabs ────────────────────────────────────────────────────────


@require_POST
def pos_tab_save(request: HttpRequest) -> HttpResponse:
    """POST /gestor/pos/tab/save/ — save the current cart on its POS tab."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse("Unauthorized", status=403)

    payload_str = request.POST.get("payload", "")
    if not payload_str:
        return HttpResponse('<span class="text-xs text-warning">Carrinho vazio</span>', status=422)

    try:
        body = json.loads(payload_str)
    except (json.JSONDecodeError, ValueError):
        return HttpResponse('<span class="text-xs text-danger">Dados inválidos</span>', status=400)

    if not body.get("items"):
        return HttpResponse('<span class="text-xs text-warning">Carrinho vazio</span>', status=422)

    try:
        result = pos_service.save_pos_tab(
            channel_ref=POS_CHANNEL_REF,
            payload=body,
            actor=f"pos:{request.user.username}",
            operator_username=request.user.username,
        )
    except PosIntentError as e:
        logger.info("pos_tab_save_intent_rejected code=%s field=%s user=%s", e.code, e.field, request.user.username)
        return HttpResponse(
            f'<span class="text-xs text-danger" data-error-code="{escape(e.code)}" data-focus-target="{escape(e.focus)}">'
            f'{escape(e.message)}</span>',
            status=e.status,
        )
    except Exception as e:
        logger.exception("pos_tab_save failed")
        return HttpResponse(f'<span class="text-xs text-danger">Erro: {e}</span>', status=422)

    response = HttpResponse(
        f'<span data-tab-code="{result.tab_code}" class="text-xs text-success font-semibold">'
        f'POS tab {result.tab_display} em uso</span>'
    )
    response["HX-Trigger"] = "posTabSaved"
    return response


@require_GET
def pos_tabs(request: HttpRequest) -> HttpResponse:
    """GET /gestor/pos/tabs/ — HTMX: POS tab grid."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse("", status=403)

    query = (request.GET.get("q") or request.GET.get("tab_code") or "").strip()
    tabs = build_pos_tabs(channel_ref=POS_CHANNEL_REF, query=query)

    return render(request, "pos/partials/tab_grid.html", {"tabs": tabs, "query": query})


@require_POST
def pos_tab_create(request: HttpRequest) -> HttpResponse:
    """POST /gestor/pos/tab/create/ — register a POS tab."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse("Unauthorized", status=403)

    try:
        tab = pos_service.register_pos_tab(
            tab_code=request.POST.get("tab_code", ""),
            label=request.POST.get("label", ""),
        )
    except Exception as e:
        logger.exception("pos_tab_create failed")
        return HttpResponse(f'<span class="text-xs text-danger">Erro: {e}</span>', status=422)

    response = HttpResponse(
        f'<span data-tab-code="{tab["tab_code"]}" class="text-xs text-success font-semibold">'
        f'POS tab {tab["tab_display"]} cadastrada</span>'
    )
    response["HX-Trigger"] = "posTabSaved"
    return response


@require_POST
def pos_tab_open(request: HttpRequest, tab_code: str = "") -> HttpResponse:
    """POST /gestor/pos/tab/open/ — open or load a POS tab as JSON."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse('{"error":"forbidden"}', content_type="application/json", status=403)

    code = tab_code or request.POST.get("tab_code", "").strip()
    try:
        payload = pos_service.open_pos_tab(
            channel_ref=POS_CHANNEL_REF,
            tab_code=code,
            actor=f"pos:{request.user.username}",
            operator_username=request.user.username,
        )
    except Exception as e:
        logger.exception("pos_tab_open failed")
        return HttpResponse(json.dumps({"error": str(e)}), content_type="application/json", status=422)

    response = HttpResponse(json.dumps(payload), content_type="application/json")
    response["HX-Trigger"] = "posTabOpened"
    return response


@require_POST
def pos_tab_clear(request: HttpRequest, session_key: str) -> HttpResponse:
    """POST /gestor/pos/tab/<key>/clear/ — make a POS tab empty again."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse("Unauthorized", status=403)

    cleared = pos_service.clear_pos_tab(
        channel_ref=POS_CHANNEL_REF,
        session_key=session_key,
        operator_username=request.user.username,
    )
    response = HttpResponse(
        '<span class="text-xs text-on-surface/50 dark:text-on-surface-dark/50">POS tab liberado</span>'
        if cleared
        else "",
        status=200 if cleared else 404,
    )
    response["HX-Trigger"] = "posTabSaved"
    return response


# ── Cash Register Views ──────────────────────────────────────────────


@require_POST
def pos_cash_open(request: HttpRequest) -> HttpResponse:
    """POST /gestor/pos/caixa/abrir/ — open a new cash register session."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse("Unauthorized", status=403)

    session = pos_cash_service.open_cash_shift(
        operator=request.user,
        opening_amount_raw=request.POST.get("opening_amount", "0"),
        terminal_ref=request.POST.get("terminal_ref", ""),
    )
    logger.info("pos_cash_open operator=%s session=%s", request.user.username, session.pk)
    return redirect("/gestor/pos/")


@require_POST
def pos_cash_sangria(request: HttpRequest) -> HttpResponse:
    """POST /gestor/pos/caixa/sangria/ — HTMX: register a cash movement."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse("Unauthorized", status=403)

    try:
        movement = pos_cash_service.register_cash_movement(
            operator=request.user,
            movement_type=request.POST.get("movement_type", "sangria"),
            amount_raw=request.POST.get("amount", "0"),
            reason=request.POST.get("reason", ""),
        )
    except POSError as exc:
        return HttpResponse(
            f'<div class="text-destructive text-sm font-semibold">{exc}</div>',
            status=422,
        )

    logger.info(
        "pos_cash_movement type=%s amount_q=%s operator=%s",
        movement.movement_type, movement.amount_q, request.user.username,
    )

    from shopman.utils.monetary import format_money as _fm
    label = {"sangria": "Sangria", "suprimento": "Suprimento", "ajuste": "Ajuste"}.get(
        movement.movement_type,
        movement.movement_type,
    )
    return HttpResponse(
        f'<div class="text-success-foreground text-sm font-semibold">'
        f'{label} de R$ {_fm(movement.amount_q)} registrada.</div>'
    )


@require_POST
def pos_cash_close(request: HttpRequest) -> HttpResponse:
    """POST /gestor/pos/caixa/fechar/ — close the current cash register session."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse("Unauthorized", status=403)

    try:
        session = pos_cash_service.close_cash_shift(
            operator=request.user,
            closing_amount_raw=request.POST.get("closing_amount", "0"),
            notes=request.POST.get("notes", ""),
        )
    except POSError as exc:
        return HttpResponse(
            f'<div class="text-destructive font-semibold">{exc}</div>',
            status=422,
        )
    logger.info("pos_cash_close operator=%s diff_q=%s", request.user.username, session.difference_q)

    return render(request, "pos/cash_close_report.html", {"session": session})
