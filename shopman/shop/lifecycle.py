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

from shopman.shop.config import ChannelConfig
from shopman.orderman.models import Directive, Order
from shopman.shop.services import (
    availability,
    customer,
    fiscal,
    fulfillment,
    loyalty,
    notification,
    payment,
    stock,
)
from shopman.shop.services.order_helpers import get_commitment_date

logger = logging.getLogger(__name__)


def has_availability_approval(order) -> bool:
    """Return True when the order carries an explicit positive availability decision."""
    decision = (order.data or {}).get("availability_decision", {})
    if decision.get("approved") is not True:
        return False
    if "decisions" in decision:
        return True
    return bool(decision.get("items"))


def ensure_confirmable(order) -> None:
    """Enforce the operational precondition for moving an order into CONFIRMED."""
    from shopman.orderman.exceptions import InvalidTransition

    if has_availability_approval(order):
        return

    raise InvalidTransition(
        code="availability_not_approved",
        message="Pedido não pode ser confirmado sem decisão positiva de disponibilidade",
        context={
            "order_ref": order.ref,
            "status": order.status,
            "availability_decision": (order.data or {}).get("availability_decision"),
        },
    )


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

    decisions = (order.data or {}).get("availability_decision", {}).get("decisions")
    if not decisions:
        decisions = [
            {
                "approved": True,
                "sku": item.get("sku"),
                "requested_qty": item.get("qty"),
                "available_qty": item.get("qty"),
                "reason_code": None,
                "is_paused": False,
                "is_planned": False,
                "target_date": get_commitment_date(order).isoformat() if get_commitment_date(order) else None,
                "failed_sku": None,
                "source": "stock.hold",
            }
            for item in order.snapshot.get("items", [])
        ]
    _record_availability_decision(
        order,
        approved=True,
        source="stock.check_on_commit" if config.stock.check_on_commit else "stock.hold",
        decisions=decisions,
    )

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
    """Order in preparation: dispatch to KDS (if enabled) + notify."""
    try:
        from shopman.shop.services import kds
        kds.dispatch(order)
    except ImportError:
        pass
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
    """Order cancelled: cancel KDS tickets (if enabled) + release stock + refund + notify."""
    try:
        from shopman.shop.services import kds
        kds.cancel_tickets(order)
    except ImportError:
        pass
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
        ensure_confirmable(order)
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
    target_date = get_commitment_date(order)
    rejected: list[tuple[str, str]] = []
    item_decisions: list[dict] = []

    for item in order.snapshot.get("items", []):
        sku = item["sku"]
        qty = item["qty"]
        status = availability.decide(
            sku,
            qty,
            channel_ref=channel_ref,
            target_date=target_date,
        )
        item_decisions.append(status)
        if not status["approved"]:
            rejected.append((sku, status.get("reason_code") or "unavailable"))

    if rejected:
        reasons = ", ".join(f"{sku}:{code}" for sku, code in rejected)
        logger.info("dispatch.on_commit: rejecting order %s — %s", order.ref, reasons)
        _record_availability_decision(
            order,
            approved=False,
            source="stock.promise_decision",
            rejected=rejected,
            decisions=item_decisions,
        )
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
        _record_availability_decision(
            order,
            approved=False,
            source="stock.verify_holds",
            rejected=[(sku, "missing_hold") for sku in sorted(missing)],
        )
        _create_alert(order, "rejected_oos")
        order.transition_status(Order.Status.CANCELLED, actor="auto_reject_oos")
        stock.release(order)
        return False

    return True


def _record_availability_decision(
    order,
    *,
    approved: bool,
    source: str,
    rejected: list[tuple[str, str]] | None = None,
    decisions: list[dict] | None = None,
) -> None:
    """Persist a lightweight audit of the operational availability decision."""
    target_date = get_commitment_date(order)
    payload = {
        "approved": approved,
        "source": source,
        "checked_at": timezone.now().isoformat(),
        "target_date": target_date.isoformat() if target_date else None,
        "channel_ref": order.channel_ref,
        "hold_ids": [entry.get("hold_id") for entry in (order.data or {}).get("hold_ids", []) if entry.get("hold_id")],
        "items": [
            {
                "sku": item.get("sku"),
                "qty": item.get("qty"),
            }
            for item in order.snapshot.get("items", [])
        ],
    }
    if decisions is not None:
        payload["decisions"] = decisions
    if rejected:
        payload["rejected"] = [
            {"sku": sku, "reason": reason}
            for sku, reason in rejected
        ]

    order.data["availability_decision"] = payload
    order.save(update_fields=["data", "updated_at"])


def _create_alert(order, alert_type: str) -> None:
    """Create an OperatorAlert for exceptional situations."""
    try:
        from shopman.shop.models import OperatorAlert

        OperatorAlert.objects.create(
            type=alert_type,
            severity="warning",
            message=f"Pedido {order.ref}: {alert_type.replace('_', ' ')}",
            order_ref=order.ref,
        )
    except Exception:
        logger.exception("lifecycle._create_alert: failed for order %s", order.ref)
