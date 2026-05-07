"""Operator order command facade.

Backstage views use this module for order mutations. Projections may still read
orders directly, but command paths should not decide lifecycle transitions in
the HTTP layer.
"""

from __future__ import annotations

import logging

from shopman.orderman.models import Order

from shopman.shop.services.cancellation import cancel
from shopman.shop.services.order_helpers import get_fulfillment_type

logger = logging.getLogger(__name__)

_NEXT_STATUS_MAP: dict[str, str] = {
    Order.Status.CONFIRMED: Order.Status.PREPARING,
    Order.Status.PREPARING: Order.Status.READY,
    Order.Status.READY: Order.Status.COMPLETED,
    Order.Status.DISPATCHED: Order.Status.DELIVERED,
    Order.Status.DELIVERED: Order.Status.COMPLETED,
}


def find_order(ref: str) -> Order | None:
    """Return an order by public reference, if it exists."""
    return Order.objects.filter(ref=ref).first()


def recent_history(*, limit: int = 20) -> list[Order]:
    """Return recent closed orders for the operator history view."""
    return list(
        Order.objects.filter(
            status__in=(
                Order.Status.COMPLETED,
                Order.Status.DELIVERED,
                Order.Status.CANCELLED,
            )
        )
        .prefetch_related("items")
        .order_by("-updated_at")[:limit]
    )


def confirm_order(order: Order, *, actor: str) -> None:
    """Confirm a manually accepted order."""
    if order.status != Order.Status.NEW:
        raise ValueError("Pedido não está aguardando confirmação")

    from shopman.shop.lifecycle import ensure_confirmable, ensure_payment_captured

    ensure_payment_captured(order)
    ensure_confirmable(order)
    order.transition_status(Order.Status.CONFIRMED, actor=actor)


def reject_order(
    order: Order,
    *,
    reason: str,
    actor: str,
    rejected_by: str,
) -> None:
    """Reject an order and queue the customer notification directive."""
    if order.status != Order.Status.NEW:
        raise ValueError("Pedido só pode ser rejeitado enquanto aguarda confirmação")

    cancel(
        order,
        reason=reason,
        actor=actor,
        extra_data={"rejected_by": rejected_by},
    )
    from shopman.shop.services import notification

    notification.send(order, "order_rejected", reason=reason, rejected_by=rejected_by)
    logger.info("operator_reject order=%s reason=%s", order.ref, reason)


def next_status_for(order: Order) -> str:
    """Return the canonical next operator-driven status, or empty string."""
    if order.status == Order.Status.READY and get_fulfillment_type(order) == "delivery":
        return Order.Status.DISPATCHED
    return _NEXT_STATUS_MAP.get(order.status, "")


def advance_order(order: Order, *, actor: str) -> str:
    """Advance an order through the operator lifecycle."""
    next_status = next_status_for(order)
    if not next_status:
        raise ValueError("Pedido não possui próxima etapa")
    if order.status == Order.Status.CONFIRMED and _requires_captured_payment_for_work(order):
        raise ValueError("Pagamento ainda não foi confirmado. Aguarde antes de iniciar o preparo.")
    order.transition_status(next_status, actor=actor)
    return next_status


def cancel_order(order: Order, *, reason: str, actor: str) -> None:
    """Cancel an order through the canonical cancellation service."""
    cancel(order, reason=reason, actor=actor)


def save_internal_notes(order: Order, *, notes: str) -> None:
    """Persist operator-only notes on the order data payload."""
    data = dict(order.data or {})
    data["internal_notes"] = notes
    order.data = data
    order.save(update_fields=["data", "updated_at"])


def _requires_captured_payment_for_work(order: Order) -> bool:
    payment = (order.data or {}).get("payment") or {}
    method = str(payment.get("method") or "").lower()
    if method not in {"pix", "card"}:
        return False
    from shopman.shop.services import payment as payment_service

    return payment_service.has_sufficient_captured_payment(order) is not True
