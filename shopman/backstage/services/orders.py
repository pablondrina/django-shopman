"""Backstage order mutation facade."""

from __future__ import annotations

from shopman.orderman.exceptions import InvalidTransition

from shopman.backstage.services.exceptions import OrderConflict, OrderError
from shopman.shop.services import operator_orders
from shopman.shop.services.operator_orders import OrderStateConflict


def find_order(ref: str):
    return operator_orders.find_order(ref)


def confirm_order(order, *, actor: str):
    try:
        return operator_orders.confirm_order(order, actor=actor)
    except OrderStateConflict as exc:
        raise OrderConflict(str(exc)) from exc
    except (ValueError, InvalidTransition) as exc:
        raise OrderError(str(exc) or "Não foi possível confirmar o pedido.") from exc


def reject_order(order, *, reason: str, actor: str, rejected_by: str, cancellation_code: str = ""):
    if not reason.strip():
        raise OrderError("Motivo obrigatório")
    try:
        return operator_orders.reject_order(
            order,
            reason=reason.strip(),
            actor=actor,
            rejected_by=rejected_by,
            cancellation_code=cancellation_code,
        )
    except OrderStateConflict as exc:
        raise OrderConflict(str(exc)) from exc
    except (ValueError, InvalidTransition) as exc:
        raise OrderError(str(exc)) from exc


def advance_order(order, *, actor: str):
    try:
        return operator_orders.advance_order(order, actor=actor)
    except (ValueError, InvalidTransition) as exc:
        # Surface the specific, operator-facing reason (advance_block_reason),
        # like confirm/reject do — never swallow it into a generic message.
        raise OrderError(str(exc) or "Ação inválida") from exc


def cancel_order(order, *, reason: str, actor: str, cancellation_code: str = "", customer_note: str = ""):
    try:
        return operator_orders.cancel_order(
            order,
            reason=reason,
            actor=actor,
            cancellation_code=cancellation_code,
            customer_note=customer_note,
        )
    except InvalidTransition as exc:
        raise OrderError(str(exc)) from exc


def cancellation_reasons(order) -> list[dict]:
    """Valid cancellation reasons for an order.

    For iFood orders, the live per-order list from the marketplace
    (``code`` + ``description``); empty for channels without reason codes.
    """
    if (order.channel_ref or "") != "ifood":
        return []
    ifood_order_id = (order.external_ref or "").strip() or (order.data or {}).get(
        "external_order_code", ""
    )
    if not ifood_order_id:
        return []
    from shopman.shop.services import ifood_callbacks

    try:
        reasons = ifood_callbacks.fetch_cancellation_reasons(ifood_order_id)
    except ifood_callbacks.IFoodCallbackError:
        return []
    return [
        {"code": str(r.get("cancelCodeId", "")), "description": r.get("description", "")}
        for r in reasons
        if r.get("cancelCodeId")
    ]


def settle_delivery_cash(order, *, operator, amount_raw: str = "", actor: str):
    from shopman.backstage.models import CashShift
    from shopman.backstage.services.pos import parse_money_to_q

    shift = CashShift.get_open_for_operator(operator)
    amount_q = parse_money_to_q(amount_raw) if str(amount_raw or "").strip() else None
    try:
        return operator_orders.settle_delivery_cash(
            order,
            cash_shift=shift,
            actor=actor,
            amount_q=amount_q,
        )
    except (ValueError, InvalidTransition) as exc:
        raise OrderError(str(exc)) from exc


def requeue_fiscal_emission(order, *, actor: str):
    try:
        from django.utils import timezone
        from shopman.orderman.models import Directive

        from shopman.shop.directives import FISCAL_EMIT_NFCE
        from shopman.shop.services import fiscal
    except Exception as exc:
        raise OrderError("Fiscal indisponível") from exc

    if (order.data or {}).get("nfce_access_key"):
        raise OrderError("NFC-e já autorizada.")
    if not ((order.data or {}).get("fiscal") or {}).get("issue_document"):
        raise OrderError("Pedido não solicitou documento fiscal.")
    if str(order.status) in ("cancelled", "returned"):
        raise OrderError("Pedido cancelado/devolvido não emite NFC-e.")

    directive = (
        Directive.objects.filter(topic=FISCAL_EMIT_NFCE, payload__order_ref=order.ref)
        .order_by("-created_at")
        .first()
    )
    if directive and directive.status == "failed":
        directive.status = "queued"
        directive.error_code = ""
        directive.last_error = ""
        directive.available_at = timezone.now()
        directive.save(update_fields=["status", "error_code", "last_error", "available_at", "updated_at"])
    else:
        fiscal.emit(order)
    order.emit_event(event_type="fiscal_requeued", actor=actor, payload={"topic": FISCAL_EMIT_NFCE})


def save_kitchen_note(order, *, notes: str):
    return operator_orders.save_kitchen_note(order, notes=notes)


def assign_order(order, *, operator_id: int, operator_name: str, actor: str):
    return operator_orders.assign_order(
        order, operator_id=operator_id, operator_name=operator_name, actor=actor
    )


def unassign_order(order, *, actor: str):
    return operator_orders.unassign_order(order, actor=actor)


def add_comment(order, *, note: str, actor: str):
    try:
        return operator_orders.add_comment(order, note=note, actor=actor)
    except ValueError as exc:
        raise OrderError(str(exc) or "Comentário inválido") from exc


def recent_history(*, limit: int = 20):
    return operator_orders.recent_history(limit=limit)


def courier_dispatch(order, *, actor: str):
    """Despacha (ou re-despacha) a corrida de entrega externa."""
    from shopman.shop.services import courier

    try:
        return courier.redispatch(order, actor=actor)
    except ValueError as exc:
        raise OrderError(str(exc) or "Não foi possível despachar a corrida.") from exc


def courier_cancel(order, *, actor: str, reason_id=None):
    """Cancela a corrida ativa na central de entregas."""
    from shopman.shop.services import courier

    try:
        return courier.cancel_ride(order, actor=actor, reason_id=reason_id)
    except ValueError as exc:
        raise OrderError(str(exc) or "Não foi possível cancelar a corrida.") from exc


def courier_quote(order) -> dict:
    """Cotação avulsa da entrega ("só cotar", sem abrir corrida)."""
    from shopman.utils.monetary import format_money

    from shopman.shop.services import courier

    estimate = courier.estimate_for_order(order, store=True)
    if estimate is None:
        raise OrderError(
            "Cotação indisponível — verifique o endereço do pedido e a "
            "conexão com a central de entregas."
        )
    return {
        "value_q": estimate["value_q"],
        "value_display": f"R$ {format_money(int(estimate['value_q']))}",
        "minutes": estimate["minutes"],
        "km": estimate["km"],
    }
