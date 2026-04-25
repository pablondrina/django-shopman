"""POS (PDV) — point of sale view for counter operations."""

from __future__ import annotations

import json
import logging

from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST
from shopman.orderman.models import Session
from shopman.utils.monetary import format_money

from shopman.backstage.constants import POS_CHANNEL_REF
from shopman.backstage.projections.pos import build_pos, build_pos_shift_summary
from shopman.shop.models import Channel
from shopman.shop.services import sessions as session_service

logger = logging.getLogger(__name__)


PERM = "backstage.operate_pos"


def _perm_required(request):
    """Redirect to login if not staff; 403 if missing operate_pos perm."""
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect(f"/admin/login/?next={request.path}")
    if not request.user.has_perm(PERM):
        return HttpResponseForbidden("Você não tem permissão para esta ação.")
    return None


def _resolve_customer(phone: str):
    """Look up customer by phone for modifier discounts."""
    try:
        from shopman.guestman.services import customer as customer_service

        return customer_service.get_by_phone(phone)
    except Exception:
        logger.exception("pos_resolve_customer_failed phone=%s", phone)
        return None


# ── Views ───────────────────────────────────────────────────────────


@require_GET
def pos_view(request: HttpRequest) -> HttpResponse:
    """GET /gestor/pos/ — main POS page."""
    denied = _perm_required(request)
    if denied:
        return denied

    from shopman.backstage.models import CashRegisterSession
    from shopman.shop.models import Shop

    shop = Shop.load()
    cash_session = CashRegisterSession.get_open_for_operator(request.user)

    if not cash_session:
        return render(request, "pos/cash_open.html", {"shop": shop})

    pos = build_pos()

    return render(request, "pos/index.html", {
        "pos": pos,
        "products": pos.products,
        "collections": pos.collections,
        "shop": shop,
        "payment_methods": pos.payment_methods,
        "cash_session": cash_session,
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
        customer = _resolve_customer(phone)
        if customer:
            name = f"{customer.first_name} {customer.last_name}".strip()
            group_ref = customer.group.ref if customer.group_id else ""
            staff_badge = ' &nbsp;<span class="text-xs text-info-foreground font-bold">(staff)</span>' if group_ref == "staff" else ""
            return HttpResponse(
                f'<span class="text-primary font-semibold" '
                f'data-customer-name="{name}" '
                f'data-customer-ref="{customer.ref}" '
                f'data-customer-group="{group_ref}">'
                f'{name}{staff_badge}'
                f'</span>'
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

    customer_name = body.get("customer_name", "").strip()
    customer_phone = body.get("customer_phone", "").strip()
    payment_method = body.get("payment_method", "cash")

    try:
        channel = Channel.objects.get(ref=POS_CHANNEL_REF)
    except Channel.DoesNotExist:
        return HttpResponse(
            f'<div class="px-3 py-2 rounded-lg bg-danger/10 border border-danger/30 text-danger text-sm font-semibold">'
            f'Canal {POS_CHANNEL_REF} não configurado. Contacte o suporte.</div>',
            status=500,
        )

    from shopman.shop.config import ChannelConfig

    config = ChannelConfig.for_channel(channel)
    session = session_service.create_session(
        channel.ref,
        handle_type="pos" if not customer_phone else "phone",
        handle_ref=customer_phone or f"pos:{request.user.username}",
    )
    session_key = session.session_key

    manual_discount = body.get("manual_discount") or {}

    ops = []
    for item in items:
        op = {
            "op": "add_line",
            "sku": item["sku"],
            "qty": int(item.get("qty", 1)),
            "unit_price_q": int(item["unit_price_q"]),
        }
        note = str(item.get("note", "") or "").strip()
        if note:
            op["meta"] = {"note": note}
        ops.append(op)

    if customer_name:
        ops.append({"op": "set_data", "path": "customer.name", "value": customer_name})
    if customer_phone:
        ops.append({"op": "set_data", "path": "customer.phone", "value": customer_phone})

    # Resolve customer for modifier discounts (employee, loyalty)
    if customer_phone:
        customer_obj = _resolve_customer(customer_phone)
        if customer_obj:
            ops.append({"op": "set_data", "path": "customer.ref", "value": customer_obj.ref})
            if customer_obj.group_id:
                ops.append({"op": "set_data", "path": "customer.group", "value": customer_obj.group.ref})

    ops.append({"op": "set_data", "path": "payment.method", "value": payment_method})
    tendered_amount_q = body.get("tendered_amount_q")
    if tendered_amount_q and payment_method == "cash":
        ops.append({"op": "set_data", "path": "payment.tendered_q", "value": int(tendered_amount_q)})
    ops.append({"op": "set_data", "path": "origin_channel", "value": "pos"})
    ops.append({"op": "set_data", "path": "fulfillment_type", "value": "pickup"})

    # Manual discount (operator-applied, with reason)
    if manual_discount and int(manual_discount.get("discount_q", 0)) > 0:
        ops.append({"op": "set_data", "path": "manual_discount.type", "value": manual_discount.get("type", "percent")})
        ops.append({"op": "set_data", "path": "manual_discount.value", "value": manual_discount.get("value", 0)})
        ops.append({"op": "set_data", "path": "manual_discount.discount_q", "value": int(manual_discount.get("discount_q", 0))})
        ops.append({"op": "set_data", "path": "manual_discount.reason", "value": manual_discount.get("reason", "")})

    try:
        session_service.modify_session(
            session_key=session_key,
            channel_ref=channel.ref,
            ops=ops,
            ctx={"actor": f"pos:{request.user.username}"},
            channel_config=config.to_dict(),
        )
    except Exception as e:
        logger.exception("pos_close modify_failed")
        return HttpResponse(
            f'<div class="px-3 py-2 rounded-lg bg-danger/10 border border-danger/30 text-danger text-sm">'
            f'<span class="font-semibold">Produto indisponível</span> — {e}'
            f'<br><span class="text-xs text-on-surface/50 dark:text-on-surface-dark/50">Remova o item e tente novamente.</span></div>'
            if ("insuficiente" in str(e).lower() or "estoque" in str(e).lower() or "stock" in str(e).lower() or "unavailable" in str(e).lower())
            else f'<div class="px-3 py-2 rounded-lg bg-danger/10 border border-danger/30 text-danger text-sm">'
            f'<span class="font-semibold">Erro ao montar pedido</span> — {e}'
            f'<br><span class="text-xs text-on-surface/50 dark:text-on-surface-dark/50">Tente novamente ou limpe o carrinho.</span></div>',
            status=422,
        )

    try:
        result = session_service.commit_session(
            session_key=session_key,
            channel_ref=channel.ref,
            idempotency_key=session_service.new_idempotency_key(),
            ctx={"actor": f"pos:{request.user.username}"},
            channel_config=config.to_dict(),
        )
    except Exception as e:
        logger.exception("pos_close commit_failed")
        return HttpResponse(
            f'<div class="px-3 py-2 rounded-lg bg-danger/10 border border-danger/30 text-danger text-sm">'
            f'<span class="font-semibold">Erro ao finalizar pedido</span> — {e}'
            f'<br><span class="text-xs text-on-surface/50 dark:text-on-surface-dark/50">Tente novamente. Se persistir, limpe o carrinho.</span></div>',
            status=400,
        )

    logger.info("pos_close order=%s total=%s", result.order_ref, result.total_q)

    total_display = f"R$ {format_money(result.total_q)}"

    # Return HTML partial with data attributes for Alpine to read
    response = HttpResponse(
        f'<div data-order-ref="{result.order_ref}" '
        f'data-total-display="{total_display}" '
        f'class="px-3 py-2 rounded-lg bg-success/10 border border-success/30 text-success text-sm font-semibold flex items-center justify-between gap-2">'
        f'<span>✓ Pedido confirmado</span>'
        f'<span class="tabular-nums">{result.order_ref} · {total_display}</span>'
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
        "last_ref": summary.last_ref,
        "last_total_display": summary.last_total_display,
    })


@require_POST
def pos_cancel_last(request: HttpRequest) -> HttpResponse:
    """POST /gestor/pos/cancel-last/ — HTMX: cancel the last POS order (within 5 min)."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse("Unauthorized", status=403)

    from datetime import timedelta

    from django.utils import timezone
    from shopman.orderman.models import Order

    from shopman.shop.services.cancellation import cancel

    order_ref = request.POST.get("order_ref", "").strip()
    if not order_ref:
        return HttpResponse(
            '<div id="pos-cancel-result" class="pos-error" '
            'style="background:var(--error-light);color:rgb(var(--error-foreground))">'
            'Refer&ecirc;ncia do pedido n&atilde;o informada</div>',
            status=422,
        )

    try:
        order = Order.objects.get(ref=order_ref)
    except Order.DoesNotExist:
        return HttpResponse(
            f'<div id="pos-cancel-result" class="pos-error" '
            f'style="background:var(--error-light);color:rgb(var(--error-foreground))">'
            f'Pedido {order_ref} n&atilde;o encontrado</div>',
            status=404,
        )

    # Only allow cancellation within 5 minutes of creation
    age = timezone.now() - order.created_at
    if age > timedelta(minutes=5):
        return HttpResponse(
            f'<div id="pos-cancel-result" class="pos-error" '
            f'style="background:var(--error-light);color:rgb(var(--error-foreground))">'
            f'Pedido {order_ref} criado h&aacute; mais de 5 minutos — cancelamento n&atilde;o permitido</div>',
            status=422,
        )

    if order.status not in ("new", "confirmed"):
        return HttpResponse(
            f'<div id="pos-cancel-result" class="pos-error" '
            f'style="background:var(--error-light);color:rgb(var(--error-foreground))">'
            f'Pedido {order_ref} n&atilde;o pode ser cancelado (status: {order.status})</div>',
            status=422,
        )

    try:
        cancel(order, reason="pos_operator", actor=f"pos:{request.user.username}")
    except Exception as e:
        logger.exception("pos_cancel_last failed for order %s", order_ref)
        return HttpResponse(
            f'<div id="pos-cancel-result" class="pos-error" '
            f'style="background:var(--error-light);color:rgb(var(--error-foreground))">'
            f'Erro ao cancelar: {e}</div>',
            status=400,
        )

    logger.info("pos_cancel_last order=%s operator=%s", order_ref, request.user.username)

    return HttpResponse(
        f'<div id="pos-cancel-result" class="pos-success" '
        f'style="background:var(--success-light,#dcfce7);color:var(--success-foreground,#166534)">'
        f'Venda {order_ref} cancelada com sucesso</div>'
    )


# ── Comandas / Parked Sessions ──────────────────────────────────────


def _build_session_ops(body: dict, username: str) -> list[dict]:
    """Build ModifyService ops from a cart payload dict."""
    ops = []
    for item in body.get("items", []):
        op = {
            "op": "add_line",
            "sku": item["sku"],
            "qty": int(item.get("qty", 1)),
            "unit_price_q": int(item["unit_price_q"]),
        }
        note = str(item.get("note", "") or "").strip()
        if note:
            op["meta"] = {"note": note}
        ops.append(op)

    customer_name = body.get("customer_name", "").strip()
    customer_phone = body.get("customer_phone", "").strip()
    if customer_name:
        ops.append({"op": "set_data", "path": "customer.name", "value": customer_name})
    if customer_phone:
        ops.append({"op": "set_data", "path": "customer.phone", "value": customer_phone})

    payment_method = body.get("payment_method", "cash")
    ops.append({"op": "set_data", "path": "payment.method", "value": payment_method})

    manual_discount = body.get("manual_discount") or {}
    if manual_discount and int(manual_discount.get("discount_q", 0)) > 0:
        ops.extend([
            {"op": "set_data", "path": "manual_discount.type", "value": manual_discount.get("type", "percent")},
            {"op": "set_data", "path": "manual_discount.value", "value": manual_discount.get("value", 0)},
            {"op": "set_data", "path": "manual_discount.discount_q", "value": int(manual_discount.get("discount_q", 0))},
            {"op": "set_data", "path": "manual_discount.reason", "value": manual_discount.get("reason", "")},
        ])
    return ops


@require_POST
def pos_park(request: HttpRequest) -> HttpResponse:
    """POST /gestor/pos/park/ — save current cart as a standby tab."""
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
        channel = Channel.objects.get(ref=POS_CHANNEL_REF)
    except Channel.DoesNotExist:
        return HttpResponse(f'<span>Canal {POS_CHANNEL_REF} não configurado</span>', status=500)

    from django.utils import timezone as tz
    from shopman.refs.generators import generate_value

    from shopman.shop.config import ChannelConfig
    from shopman.shop.models import Shop

    shop = Shop.load()
    config = ChannelConfig.for_channel(channel)

    tab = generate_value("POS_TAB", {
        "store_id": str(shop.pk),
        "business_date": tz.localdate().isoformat(),
    })

    session = session_service.create_session(
        channel.ref,
        handle_type="pos",
        handle_ref=f"pos:{request.user.username}",
    )
    session_key = session.session_key
    session_service.assign_handle(
        session_key=session_key,
        channel_ref=channel.ref,
        handle_type="pos",
        handle_ref=f"pos:{request.user.username}:{session_key[:8]}",
    )

    ops = _build_session_ops(body, request.user.username)
    ops.extend([
        {"op": "set_data", "path": "standby", "value": True},
        {"op": "set_data", "path": "tab", "value": tab},
        {"op": "set_data", "path": "standby_operator", "value": request.user.username},
    ])

    try:
        session_service.modify_session(
            session_key=session_key,
            channel_ref=channel.ref,
            ops=ops,
            ctx={"actor": f"pos:{request.user.username}"},
            channel_config=config.to_dict(),
        )
    except Exception as e:
        logger.exception("pos_park modify_failed")
        return HttpResponse(f'<span class="text-xs text-danger">Erro: {e}</span>', status=422)

    logger.info("pos_park tab=%s session=%s operator=%s", tab, session_key, request.user.username)

    response = HttpResponse(
        f'<span data-tab="{tab}" class="text-xs text-success font-semibold">'
        f'Tab {tab} em standby</span>'
    )
    response["HX-Trigger"] = "sessionParked"
    return response


@require_GET
def pos_sessions(request: HttpRequest) -> HttpResponse:
    """GET /gestor/pos/sessions/ — HTMX: standby session tab list."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse("", status=403)

    from django.utils import timezone as tz
    from shopman.utils.monetary import format_money as _fm

    sessions_qs = Session.objects.filter(
        channel_ref=POS_CHANNEL_REF,
        state="open",
        data__standby=True,
        opened_at__date=tz.localdate(),
    ).order_by("opened_at")

    sessions = []
    for s in sessions_qs:
        data = s.data or {}
        items = s.items or []
        item_count = sum(int(it.get("qty", 1)) for it in items)
        total_q = sum(int(it.get("qty", 1)) * int(it.get("unit_price_q", 0)) for it in items)
        discount_q = int((data.get("manual_discount") or {}).get("discount_q", 0))
        sessions.append({
            "session_key": s.session_key,
            "tab": data.get("tab", "?"),
            "item_count": item_count,
            "total_display": f"R$ {_fm(max(0, total_q - discount_q))}",
            "customer_name": (data.get("customer") or {}).get("name", ""),
        })

    return render(request, "pos/partials/session_tabs.html", {"sessions": sessions})


@require_GET
def pos_load_session(request: HttpRequest, session_key: str) -> HttpResponse:
    """GET /gestor/pos/session/<key>/load/ — return session data as JSON for Alpine."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse('{"error":"forbidden"}', content_type="application/json", status=403)

    try:
        session = Session.objects.get(
            session_key=session_key,
            channel_ref=POS_CHANNEL_REF,
            state="open",
        )
    except Session.DoesNotExist:
        return HttpResponse('{"error":"not_found"}', content_type="application/json", status=404)

    data = session.data or {}
    customer = data.get("customer") or {}
    payment = data.get("payment") or {}
    discount = data.get("manual_discount") or {}

    items = [
        {
            "sku": it["sku"],
            "name": it.get("name", it["sku"]),
            "price_q": it.get("unit_price_q", 0),
            "qty": int(it.get("qty", 1)),
            "note": (it.get("meta") or {}).get("note", ""),
            "is_d1": False,
        }
        for it in (session.items or [])
    ]

    session.data["standby"] = False
    session.save(update_fields=["data"])

    import json as _json
    payload = _json.dumps({
        "session_key": session_key,
        "tab": data.get("tab", ""),
        "items": items,
        "customer_phone": customer.get("phone", ""),
        "customer_name": customer.get("name", ""),
        "customer_group": customer.get("group", ""),
        "payment_method": payment.get("method", "cash"),
        "discount_type": discount.get("type", "percent"),
        "discount_value": str(discount.get("value", "")) if discount.get("value") else "",
        "discount_reason": discount.get("reason", "cortesia"),
    })
    response = HttpResponse(payload, content_type="application/json")
    response["HX-Trigger"] = "sessionLoaded"
    return response


# ── Cash Register Views ──────────────────────────────────────────────


@require_POST
def pos_cash_open(request: HttpRequest) -> HttpResponse:
    """POST /gestor/pos/caixa/abrir/ — open a new cash register session."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse("Unauthorized", status=403)

    from shopman.backstage.models import CashRegisterSession

    existing = CashRegisterSession.get_open_for_operator(request.user)
    if existing:
        return redirect("/gestor/pos/")

    try:
        opening_raw = request.POST.get("opening_amount", "0").strip().replace(",", ".")
        opening_amount_q = round(float(opening_raw) * 100)
    except (ValueError, TypeError):
        opening_amount_q = 0

    CashRegisterSession.objects.create(
        operator=request.user,
        opening_amount_q=max(0, opening_amount_q),
    )
    logger.info("pos_cash_open operator=%s opening_q=%s", request.user.username, opening_amount_q)
    return redirect("/gestor/pos/")


@require_POST
def pos_cash_sangria(request: HttpRequest) -> HttpResponse:
    """POST /gestor/pos/caixa/sangria/ — HTMX: register a cash movement."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse("Unauthorized", status=403)

    from shopman.backstage.models import CashMovement, CashRegisterSession

    session = CashRegisterSession.get_open_for_operator(request.user)
    if not session:
        return HttpResponse(
            '<div class="text-destructive text-sm font-semibold">Caixa não aberto.</div>',
            status=422,
        )

    movement_type = request.POST.get("movement_type", "sangria")
    if movement_type not in ("sangria", "suprimento", "ajuste"):
        movement_type = "sangria"

    try:
        amount_raw = request.POST.get("amount", "0").strip().replace(",", ".")
        amount_q = round(float(amount_raw) * 100)
    except (ValueError, TypeError):
        amount_q = 0

    if amount_q <= 0:
        return HttpResponse(
            '<div class="text-destructive text-sm font-semibold">Valor inválido.</div>',
            status=422,
        )

    reason = request.POST.get("reason", "").strip()
    CashMovement.objects.create(
        session=session,
        movement_type=movement_type,
        amount_q=amount_q,
        reason=reason,
        created_by=request.user.username,
    )
    logger.info(
        "pos_cash_movement type=%s amount_q=%s operator=%s",
        movement_type, amount_q, request.user.username,
    )

    from shopman.utils.monetary import format_money as _fm
    label = {"sangria": "Sangria", "suprimento": "Suprimento", "ajuste": "Ajuste"}.get(movement_type, movement_type)
    return HttpResponse(
        f'<div class="text-success-foreground text-sm font-semibold">'
        f'{label} de R$ {_fm(amount_q)} registrada.</div>'
    )


@require_POST
def pos_cash_close(request: HttpRequest) -> HttpResponse:
    """POST /gestor/pos/caixa/fechar/ — close the current cash register session."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse("Unauthorized", status=403)

    from shopman.backstage.models import CashRegisterSession

    session = CashRegisterSession.get_open_for_operator(request.user)
    if not session:
        return HttpResponse(
            '<div class="text-destructive font-semibold">Caixa não aberto.</div>',
            status=422,
        )

    try:
        closing_raw = request.POST.get("closing_amount", "0").strip().replace(",", ".")
        closing_amount_q = round(float(closing_raw) * 100)
    except (ValueError, TypeError):
        closing_amount_q = 0

    notes = request.POST.get("notes", "").strip()
    session.close(closing_amount_q=closing_amount_q, notes=notes)
    logger.info("pos_cash_close operator=%s closing_q=%s diff_q=%s", request.user.username, closing_amount_q, session.difference_q)

    return render(request, "pos/cash_close_report.html", {"session": session})
