"""Backstage order mutation facade."""

from __future__ import annotations

from shopman.orderman.exceptions import InvalidTransition

from shopman.backstage.services.exceptions import OrderError
from shopman.shop.services import operator_orders


def find_order(ref: str):
    return operator_orders.find_order(ref)


def confirm_order(order, *, actor: str):
    return operator_orders.confirm_order(order, actor=actor)


def reject_order(order, *, reason: str, actor: str, rejected_by: str):
    if not reason.strip():
        raise OrderError("Motivo obrigatório")
    try:
        return operator_orders.reject_order(
            order,
            reason=reason.strip(),
            actor=actor,
            rejected_by=rejected_by,
        )
    except (ValueError, InvalidTransition) as exc:
        raise OrderError(str(exc)) from exc


def advance_order(order, *, actor: str):
    try:
        return operator_orders.advance_order(order, actor=actor)
    except (ValueError, InvalidTransition) as exc:
        raise OrderError("Ação inválida") from exc


def cancel_order(order, *, reason: str, actor: str):
    try:
        return operator_orders.cancel_order(order, reason=reason, actor=actor)
    except InvalidTransition as exc:
        raise OrderError(str(exc)) from exc


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


def save_internal_notes(order, *, notes: str):
    return operator_orders.save_internal_notes(order, notes=notes)


def recent_history(*, limit: int = 20):
    return operator_orders.recent_history(limit=limit)
