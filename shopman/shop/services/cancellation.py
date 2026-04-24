"""
Cancellation service — single entry point for all cancellation paths.

Core: Order.transition_status()
"""

from __future__ import annotations

import logging

from shopman.orderman.models import Order

logger = logging.getLogger(__name__)


def cancel(
    order,
    reason: str,
    actor: str = "system",
    *,
    extra_data: dict | None = None,
) -> bool:
    """
    Cancel an order. Single entry point for all cancellation paths:
    - Customer self-cancel
    - Operator reject / cancel
    - PIX / payment timeout

    Transitions the order to CANCELLED. The Flow.on_cancelled() handler
    releases stock via ``stock.release`` (``order.data[\"hold_ids\"]``).

    Args:
        order: The Order to cancel.
        reason: Reason for cancellation (stored in order.data).
        actor: Who initiated the cancellation.
        extra_data: Optional keys merged into ``order.data`` (e.g. ``rejected_by``).

    Returns:
        True if cancelled, False if order was already in a terminal state.

    SYNC — transitions status immediately.
    """
    if order.status in (Order.Status.CANCELLED, Order.Status.COMPLETED):
        logger.info(
            "cancellation.cancel: order %s already %s, skipping",
            order.ref, order.status,
        )
        return False

    # Write cancellation context FIRST — transition_status fires the
    # order_changed signal via on_commit, and lifecycle handlers need
    # cancellation_reason and cancelled_by already in order.data.
    data = dict(order.data or {})
    data["cancellation_reason"] = reason
    data["cancelled_by"] = actor
    if extra_data:
        data.update(extra_data)
    order.data = data
    order.save(update_fields=["data", "updated_at"])

    order.transition_status(Order.Status.CANCELLED, actor=actor)

    logger.info("cancellation.cancel: order %s cancelled by %s — %s", order.ref, actor, reason)
    return True
