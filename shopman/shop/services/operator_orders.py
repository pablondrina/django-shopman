"""Operator order command facade.

Backstage views use this module for order mutations. Projections may still read
orders directly, but command paths should not decide lifecycle transitions in
the HTTP layer.
"""

from __future__ import annotations

import logging

from shopman.orderman.models import Directive, Order

from shopman.shop.services.cancellation import cancel
from shopman.shop.services.order_helpers import get_fulfillment_type

logger = logging.getLogger(__name__)

NOTIFICATION_SEND = "notification.send"

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
    cancel(
        order,
        reason=reason,
        actor=actor,
        extra_data={"rejected_by": rejected_by},
    )
    Directive.objects.create(
        topic=NOTIFICATION_SEND,
        payload={
            "order_ref": order.ref,
            "template": "order_rejected",
            "reason": reason,
        },
    )
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
    order.transition_status(next_status, actor=actor)
    return next_status


def save_internal_notes(order: Order, *, notes: str) -> None:
    """Persist operator-only notes on the order data payload."""
    data = dict(order.data or {})
    data["internal_notes"] = notes
    order.data = data
    order.save(update_fields=["data", "updated_at"])


def mark_paid(order: Order, *, actor: str, operator_username: str) -> bool:
    """Mark an offline payment as received and run paid lifecycle hooks.

    Returns False when the order was already marked paid.
    """
    payment_data = dict((order.data or {}).get("payment", {}))
    if payment_data.get("marked_paid_by"):
        return False

    payment_data["marked_paid_by"] = operator_username
    data = dict(order.data or {})
    data["payment"] = payment_data
    order.data = data
    order.save(update_fields=["data", "updated_at"])

    if order.status == Order.Status.NEW:
        from shopman.shop.lifecycle import ensure_confirmable

        ensure_confirmable(order)
        order.transition_status(Order.Status.CONFIRMED, actor=actor)

    logger.info("mark_paid order=%s operator=%s", order.ref, operator_username)

    from shopman.shop.lifecycle import dispatch

    dispatch(order, "on_paid")
    return True
