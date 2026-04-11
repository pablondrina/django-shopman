"""
Declarative dispatch — lifecycle coordination for orders.

Signal `order_changed` → dispatch(order, phase) → services.

dispatch() reads ChannelConfig and calls the appropriate services based on
payment.timing, fulfillment.timing, confirmation.mode, and stock.check_on_commit.

No Flow classes — behavior is purely configuration-driven.

Timing × Phase table:
    payment.timing:
        "external"    → no payment.initiate (counter/marketplace)
        "at_commit"   → payment.initiate on commit
        "post_commit" → payment.initiate on confirmed (default)

    fulfillment.timing:
        "at_commit"   → fulfillment.create on commit
        "post_commit" → fulfillment.create on ready (default)
        "external"    → no fulfillment.create

    stock.check_on_commit:
        True  → per-item availability check before stock.hold (POS, marketplace)
        False → skip check (web storefront validates during checkout)

    confirmation.mode:
        "immediate"   → auto-confirm on commit
        "optimistic"  → auto-confirm after timeout if not cancelled
        "manual"      → wait for operator
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from shopman.config import ChannelConfig
from shopman.orderman.models import Directive, Order
from shopman.services import (
    availability,
    customer,
    fiscal,
    fulfillment,
    kds,
    loyalty,
    notification,
    payment,
    stock,
)

logger = logging.getLogger(__name__)


def dispatch(order, phase: str) -> None:
    """Resolve ChannelConfig and call services for the given phase.

    Exceptions propagate — an order stuck in an inconsistent state is worse
    than a visible error. Callers (signal handlers) are responsible for
    surfacing failures appropriately.
    """
    config = ChannelConfig.for_channel(order.channel_ref)

    handler = _PHASE_HANDLERS.get(phase)
    if handler is None:
        logger.warning("dispatch: unknown phase %s for order %s", phase, order.ref)
        return
    handler(order, config)


# ── Phase handlers ──


def _on_commit(order, config: ChannelConfig) -> None:
    """Order created: ensure customer, check availability, hold stock,
    redeem loyalty, handle confirmation."""
    customer.ensure(order)

    if config.stock.check_on_commit:
        if not _check_availability(order, config):
            return  # order cancelled

    stock.hold(order)

    if config.stock.check_on_commit and (order.data or {}).get("hold_ids"):
        if not _verify_holds(order):
            return  # order cancelled

    loyalty.redeem(order)

    if config.payment.timing == "at_commit":
        payment.initiate(order)
    if config.fulfillment.timing == "at_commit":
        fulfillment.create(order)

    _handle_confirmation(order, config)


def _on_confirmed(order, config: ChannelConfig) -> None:
    """Order confirmed: initiate payment (if post_commit), fulfill stock
    (if no digital payment), notify."""
    if config.payment.timing == "post_commit":
        payment.initiate(order)
    if config.payment.timing == "external" and config.payment.method != "external":
        # Counter payment — no digital payment step, fulfill immediately
        stock.fulfill(order)
    notification.send(order, "order_confirmed")


def _on_paid(order, config: ChannelConfig) -> None:
    """Payment confirmed (via webhook).

    Handles race condition: if order was already cancelled,
    refund and alert instead.
    """
    if order.status == Order.Status.CANCELLED:
        payment.refund(order)
        _create_alert(order, "payment_after_cancel")
        return
    stock.fulfill(order)
    notification.send(order, "payment_confirmed")


def _on_preparing(order, config: ChannelConfig) -> None:
    """Order in preparation: dispatch to KDS + notify."""
    kds.dispatch(order)
    notification.send(order, "order_preparing")


def _on_ready(order, config: ChannelConfig) -> None:
    """Order ready: create fulfillment (if post_commit) + notify."""
    if config.fulfillment.timing == "post_commit":
        fulfillment.create(order)
    notification.send(order, "order_ready")


def _on_dispatched(order, config: ChannelConfig) -> None:
    """Order dispatched: notify."""
    notification.send(order, "order_dispatched")


def _on_delivered(order, config: ChannelConfig) -> None:
    """Order delivered: notify."""
    notification.send(order, "order_delivered")


def _on_completed(order, config: ChannelConfig) -> None:
    """Order completed: loyalty points + fiscal emission."""
    loyalty.earn(order)
    fiscal.emit(order)


def _on_cancelled(order, config: ChannelConfig) -> None:
    """Order cancelled: cancel KDS tickets + release stock + refund + notify."""
    kds.cancel_tickets(order)
    stock.release(order)
    payment.refund(order)
    notification.send(order, "order_cancelled")


def _on_returned(order, config: ChannelConfig) -> None:
    """Order returned: revert stock + refund + cancel fiscal + notify."""
    stock.revert(order)
    payment.refund(order)
    fiscal.cancel(order)
    notification.send(order, "order_returned")


_PHASE_HANDLERS = {
    "on_commit": _on_commit,
    "on_confirmed": _on_confirmed,
    "on_paid": _on_paid,
    "on_preparing": _on_preparing,
    "on_ready": _on_ready,
    "on_dispatched": _on_dispatched,
    "on_delivered": _on_delivered,
    "on_completed": _on_completed,
    "on_cancelled": _on_cancelled,
    "on_returned": _on_returned,
}


# ── Helpers ──


def _handle_confirmation(order, config: ChannelConfig) -> None:
    """Route confirmation by mode: immediate, optimistic, manual."""
    mode = config.confirmation.mode

    if mode == "immediate":
        order.transition_status(Order.Status.CONFIRMED, actor="auto_confirm")
    elif mode == "optimistic":
        expires_at = timezone.now() + timedelta(minutes=config.confirmation.timeout_minutes)
        Directive.objects.create(
            topic="confirmation.timeout",
            payload={
                "order_ref": order.ref,
                "action": "confirm",
                "expires_at": expires_at.isoformat(),
            },
            available_at=expires_at,
        )
    # manual: wait for operator — no action


def _check_availability(order, config: ChannelConfig) -> bool:
    """Per-item availability check. Returns False if order was cancelled."""
    channel_ref = order.channel_ref or None
    rejected: list[tuple[str, str]] = []

    for item in order.snapshot.get("items", []):
        sku = item["sku"]
        qty = item["qty"]
        status = availability.check(sku, qty, channel_ref=channel_ref)
        if not status["ok"]:
            rejected.append((sku, status.get("error_code") or "unavailable"))

    if rejected:
        reasons = ", ".join(f"{sku}:{code}" for sku, code in rejected)
        logger.info("dispatch.on_commit: rejecting order %s — %s", order.ref, reasons)
        _create_alert(order, "rejected_unavailable")
        order.transition_status(Order.Status.CANCELLED, actor="auto_reject_unavailable")
        return False

    return True


def _verify_holds(order) -> bool:
    """Defense-in-depth: verify held SKUs match ordered SKUs after stock.hold().
    Returns False if order was cancelled."""
    held_skus = {h.get("sku") for h in (order.data or {}).get("hold_ids", [])}
    ordered_skus = {item["sku"] for item in order.snapshot.get("items", [])}
    missing = ordered_skus - held_skus

    if missing:
        _create_alert(order, "rejected_oos")
        order.transition_status(Order.Status.CANCELLED, actor="auto_reject_oos")
        stock.release(order)
        return False

    return True


def _create_alert(order, alert_type: str) -> None:
    """Create an OperatorAlert for exceptional situations."""
    try:
        from shopman.models import OperatorAlert

        OperatorAlert.objects.create(
            type=alert_type,
            severity="warning",
            message=f"Pedido {order.ref}: {alert_type.replace('_', ' ')}",
            order_ref=order.ref,
        )
    except Exception:
        logger.exception("lifecycle._create_alert: failed for order %s", order.ref)
