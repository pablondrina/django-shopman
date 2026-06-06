"""POS (PDV) — point of sale view for counter operations.

Views own transport: HTTP status, ``HX-Trigger`` headers, JSON bodies. The HTML
fragments these endpoints answer with are shaped by ``presentation.pos`` and
rendered from ``templates/pos/partials/fragments/`` — no HTML is built here.
"""

from __future__ import annotations

import json
import logging

from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from shopman.backstage.constants import POS_CHANNEL_REF
from shopman.backstage.presentation import pos as pos_fragments
from shopman.backstage.projections import pos as pos_projection
from shopman.backstage.projections.pos import build_pos, build_pos_shift_summary, build_pos_tabs
from shopman.backstage.services import operator as operator_service
from shopman.backstage.services import pos as pos_cash_service
from shopman.backstage.services.exceptions import POSError
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import PosIntentError

logger = logging.getLogger(__name__)


PERM = "backstage.operate_pos"


def _fragment(frag, *, status: int = 200, trigger: str | None = None) -> HttpResponse:
    """Render a presentation fragment view-model into an HTMX response."""
    response = HttpResponse(render_to_string(frag.TEMPLATE, {"frag": frag}), status=status)
    if trigger:
        response["HX-Trigger"] = trigger
    return response


def _pos_error_response(exc: PosIntentError, *, fallback_status: int = 422) -> HttpResponse:
    """Render a POS validation error with stable recovery metadata."""
    status = getattr(exc, "status", None) or fallback_status
    return _fragment(pos_fragments.intent_error(exc), status=status)


def _cash_shift_required_response() -> HttpResponse:
    return _fragment(pos_fragments.cash_shift_required(), status=409)


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
    cash_shift = CashShift.get_open_for_operator(request.user)

    if not cash_shift:
        return render(request, "pos/cash_open.html", {"shop": shop})

    pos = build_pos(terminal=cash_shift.terminal)

    return render(request, "pos/index.html", {
        "pos": pos,
        "products": pos.products,
        "collections": pos.collections,
        "shop": shop,
        "payment_methods": pos.payment_methods,
        "cash_shift": cash_shift,
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
        return _fragment(pos_fragments.customer_anon())

    try:
        customer = pos_service.resolve_customer(phone)
        if customer:
            summary = pos_projection.customer_history_summary(customer.ref)
            return _fragment(
                pos_fragments.customer_found(
                    customer,
                    summary=summary,
                    default_address=customer.default_address,
                )
            )
    except Exception:
        logger.exception("pos_customer_lookup failed")

    return _fragment(pos_fragments.customer_missing())


@require_POST
def pos_close(request: HttpRequest) -> HttpResponse:
    """POST /gestor/pos/close/ — HTMX: create order, return result partial."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse("Unauthorized", status=403)

    # Parse payload from hx-vals
    payload_str = request.POST.get("payload", "")
    if not payload_str:
        return _fragment(pos_fragments.empty_cart(), status=422)

    try:
        body = json.loads(payload_str)
    except (json.JSONDecodeError, ValueError):
        return _fragment(pos_fragments.invalid_payload(), status=400)

    items = body.get("items", [])
    if not items:
        return _fragment(pos_fragments.empty_cart(), status=422)

    from shopman.backstage.models import CashShift

    cash_shift = CashShift.get_open_for_operator(request.user)
    if not cash_shift:
        return _cash_shift_required_response()
    body["cash_shift_id"] = cash_shift.pk
    body["pos_terminal_ref"] = cash_shift.terminal.ref

    try:
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
            return _fragment(pos_fragments.channel_error(str(e)), status=500)
        is_stock_error = (
            "insuficiente" in lower
            or "estoque" in lower
            or "stock" in lower
            or "unavailable" in lower
        )
        return _fragment(
            pos_fragments.sale_error(str(e), is_stock=is_stock_error),
            status=422 if is_stock_error else 400,
        )

    order_url = reverse("admin_console_order_detail", args=[result.order_ref])
    return _fragment(
        pos_fragments.order_confirmed(result, order_url=order_url),
        trigger="posOrderCreated",
    )


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
        return _fragment(pos_fragments.cancel_missing_ref(), status=422)

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
        return _fragment(pos_fragments.cancel_error(str(e)), status=status)

    return _fragment(pos_fragments.cancel_done(order_ref))


# ── POS Tabs ────────────────────────────────────────────────────────


@require_POST
def pos_tab_save(request: HttpRequest) -> HttpResponse:
    """POST /gestor/pos/tab/save/ — save the current cart on its POS tab."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse("Unauthorized", status=403)

    payload_str = request.POST.get("payload", "")
    if not payload_str:
        return _fragment(pos_fragments.empty_cart_inline(), status=422)

    try:
        body = json.loads(payload_str)
    except (json.JSONDecodeError, ValueError):
        return _fragment(pos_fragments.invalid_payload_inline(), status=400)

    if not body.get("items"):
        return _fragment(pos_fragments.empty_cart_inline(), status=422)

    try:
        result = pos_service.save_pos_tab(
            channel_ref=POS_CHANNEL_REF,
            payload=body,
            actor=f"pos:{request.user.username}",
            operator_username=request.user.username,
        )
    except PosIntentError as e:
        logger.info("pos_tab_save_intent_rejected code=%s field=%s user=%s", e.code, e.field, request.user.username)
        return _fragment(pos_fragments.tab_intent_error(e), status=e.status)
    except Exception as e:
        logger.exception("pos_tab_save failed")
        return _fragment(pos_fragments.tab_generic_error(str(e)), status=422)

    return _fragment(
        pos_fragments.tab_saved(tab_display=result.tab_display, tab_ref=result.tab_ref),
        trigger="posTabSaved",
    )


@require_GET
def pos_tabs(request: HttpRequest) -> HttpResponse:
    """GET /gestor/pos/tabs/ — HTMX: POS tab grid."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse("", status=403)

    query = (request.GET.get("q") or request.GET.get("tab_ref") or "").strip()
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
            tab_ref=request.POST.get("tab_ref", ""),
            label=request.POST.get("label", ""),
        )
    except Exception as e:
        logger.exception("pos_tab_create failed")
        return _fragment(pos_fragments.tab_generic_error(str(e)), status=422)

    return _fragment(
        pos_fragments.tab_created(tab_display=tab["tab_display"], tab_ref=tab["tab_ref"]),
        trigger="posTabSaved",
    )


@require_POST
def pos_tab_open(request: HttpRequest, tab_ref: str = "") -> HttpResponse:
    """POST /gestor/pos/tab/open/ — open or load a POS tab as JSON."""
    denied = _perm_required(request)
    if denied:
        return HttpResponse('{"error":"forbidden"}', content_type="application/json", status=403)

    ref = tab_ref or request.POST.get("tab_ref", "").strip()
    try:
        session = pos_service.open_pos_tab(
            channel_ref=POS_CHANNEL_REF,
            tab_ref=ref,
            actor=f"pos:{request.user.username}",
            operator_username=request.user.username,
        )
    except Exception as e:
        logger.exception("pos_tab_open failed")
        return HttpResponse(json.dumps({"error": str(e)}), content_type="application/json", status=422)

    response = HttpResponse(json.dumps(pos_projection.build_open_tab(session)), content_type="application/json")
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
    if cleared:
        response = _fragment(pos_fragments.tab_cleared(), trigger="posTabSaved")
    else:
        response = HttpResponse("", status=404)
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
        return _fragment(pos_fragments.cash_movement_error(str(exc)), status=422)

    logger.info(
        "pos_cash_movement type=%s amount_q=%s operator=%s",
        movement.movement_type, movement.amount_q, request.user.username,
    )
    return _fragment(pos_fragments.cash_movement_done(movement))


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
        return _fragment(pos_fragments.cash_close_error(str(exc)), status=422)
    logger.info("pos_cash_close operator=%s diff_q=%s", request.user.username, session.difference_q)

    return render(request, "pos/cash_close_report.html", {"session": session})


# ── Operator identity (PIN lock screen) ─────────────────────────────


@require_POST
def pos_operator_unlock(request: HttpRequest) -> HttpResponse:
    """POST /gestor/pos/operator/unlock/ — claim the terminal as an operator via PIN."""
    denied = _perm_required(request)
    if denied:
        return JsonResponse({"ok": False, "error": {"code": "forbidden"}}, status=403)

    operator_id = request.POST.get("operator_id", "").strip()
    pin = request.POST.get("pin", "")

    operator = get_user_model().objects.filter(pk=operator_id, is_active=True).first() if operator_id else None
    if operator is None or not operator_service.verify_operator_pin(operator, pin):
        logger.info("pos_operator_unlock rejected operator_id=%s", operator_id or "-")
        return JsonResponse(
            {"ok": False, "error": {"code": "operator_pin_invalid", "message": "PIN inválido."}},
            status=403,
        )

    card = operator_service.set_active_operator(request, operator)
    logger.info("pos_operator_unlock operator=%s", operator.get_username())
    return JsonResponse({"ok": True, "operator": card})


@require_POST
def pos_operator_lock(request: HttpRequest) -> HttpResponse:
    """POST /gestor/pos/operator/lock/ — lock the terminal (drop active operator)."""
    denied = _perm_required(request)
    if denied:
        return JsonResponse({"ok": False, "error": {"code": "forbidden"}}, status=403)
    operator_service.clear_active_operator(request)
    return JsonResponse({"ok": True})
