"""
Flow hierarchy — lifecycle coordination for orders.

Each Flow class defines the phases an order goes through.
Services are called directly (no indirection). The Flow is pure domain.

Signal `order_changed` → dispatch() → Flow.on_<phase>() → services.

Hierarchy:
    BaseFlow                   # Full lifecycle — 10 phases
    ├── LocalFlow              # In-person — immediate confirmation, no digital payment
    │   ├── PosFlow            # Counter
    │   └── TotemFlow          # Self-service
    ├── RemoteFlow             # Remote — payment required, active notification
    │   ├── WebFlow            # E-commerce
    │   ├── WhatsAppFlow       # WhatsApp (via ManyChat)
    │   └── ManychatFlow       # ManyChat generic
    └── MarketplaceFlow        # Marketplace — external payment, pessimistic confirmation
        └── IFoodFlow          # iFood
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from shopman.ordering.models import Directive, Order
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

# ── Registry ──

_registry: dict[str, type] = {}


def flow(name: str):
    """Decorator that registers a Flow class in the registry."""
    def decorator(cls):
        _registry[name] = cls
        cls.name = name
        return cls
    return decorator


def get_flow(order) -> BaseFlow:
    """Resolve the Flow class for an order based on channel config."""
    flow_name = _channel_config(order, "flow", "base")
    cls = _registry.get(flow_name, BaseFlow)
    return cls()


def dispatch(order, phase: str) -> None:
    """Resolve Flow and call the phase method."""
    flow_instance = get_flow(order)
    method = getattr(flow_instance, phase, None)
    if method is None:
        logger.warning("flows.dispatch: no phase %s on %s", phase, type(flow_instance).__name__)
        return
    try:
        method(order)
    except Exception:
        logger.exception(
            "flows.dispatch: error in %s.%s for order %s",
            type(flow_instance).__name__, phase, order.ref,
        )


# ── Helpers ──


def _channel_config(order, key: str, default=None):
    """Read a key from the order's channel config."""
    config = getattr(order.channel, "config", None) or {}
    return config.get(key, default)


# ── BaseFlow ──


@flow("base")
class BaseFlow:
    """Full lifecycle — 10 phases."""

    def on_commit(self, order):
        """Order created: ensure customer, hold stock, handle confirmation, redeem loyalty."""
        customer.ensure(order)
        stock.hold(order)
        loyalty.redeem(order)
        self.handle_confirmation(order)

    def handle_confirmation(self, order):
        """Route confirmation by mode: immediate, optimistic, pessimistic."""
        mode = _channel_config(order, "confirmation_mode", "immediate")
        timeout = _channel_config(order, "confirmation_timeout", 300)

        if mode == "immediate":
            order.transition_status(Order.Status.CONFIRMED, actor="auto_confirm")
        elif mode == "optimistic":
            expires_at = timezone.now() + timedelta(seconds=timeout)
            Directive.objects.create(
                topic="confirmation.timeout",
                payload={
                    "order_ref": order.ref,
                    "action": "confirm",
                    "expires_at": expires_at.isoformat(),
                },
                available_at=expires_at,
            )
        # pessimistic: wait for operator — no action

    def on_confirmed(self, order):
        """Order confirmed: initiate payment + notify."""
        payment.initiate(order)
        notification.send(order, "order_confirmed")

    def on_paid(self, order):
        """Payment confirmed (via webhook, not status transition).

        Handles race condition: if order was already cancelled,
        refund and alert instead.
        """
        if order.status == Order.Status.CANCELLED:
            payment.refund(order)
            _create_alert(order, "payment_after_cancel")
            return
        stock.fulfill(order)
        notification.send(order, "payment_confirmed")

    def on_preparing(self, order):
        """Order in preparation: dispatch to KDS + notify."""
        kds.dispatch(order)
        notification.send(order, "order_preparing")

    def on_ready(self, order):
        """Order ready: create fulfillment + notify."""
        fulfillment.create(order)
        notification.send(order, "order_ready")

    def on_dispatched(self, order):
        """Order dispatched: notify."""
        notification.send(order, "order_dispatched")

    def on_delivered(self, order):
        """Order delivered: notify."""
        notification.send(order, "order_delivered")

    def on_completed(self, order):
        """Order completed: loyalty points + fiscal emission."""
        loyalty.earn(order)
        fiscal.emit(order)

    def on_cancelled(self, order):
        """Order cancelled: cancel KDS tickets + release stock + refund + notify.

        Cancels open KDS tickets first to prevent kitchen from producing items
        for a cancelled order (tickets would otherwise become orphans).
        """
        kds.cancel_tickets(order)
        stock.release(order)
        payment.refund(order)
        notification.send(order, "order_cancelled")

    def on_returned(self, order):
        """Order returned: revert stock + refund + cancel fiscal + notify."""
        stock.revert(order)
        payment.refund(order)
        fiscal.cancel(order)
        notification.send(order, "order_returned")


# ── LocalFlow ──


@flow("local")
class LocalFlow(BaseFlow):
    """In-person — immediate confirmation, no digital payment."""

    def on_commit(self, order):
        customer.ensure(order)

        # Per-item availability check — symmetric with MarketplaceFlow.on_commit.
        # POS operators see stock visually but this gate prevents inconsistencies
        # when a product is paused or stock is depleted between display and commit.
        channel_ref = getattr(order.channel, "ref", None)
        for item in order.snapshot.get("items", []):
            sku = item["sku"]
            qty = item["qty"]
            status = availability.check(sku, qty, channel_ref=channel_ref)
            if not status["ok"]:
                logger.info(
                    "LocalFlow.on_commit: rejecting order %s — sku=%s code=%s",
                    order.ref, sku, status.get("error_code"),
                )
                _create_alert(order, "pos_rejected_unavailable")
                order.transition_status(Order.Status.CANCELLED, actor="auto_reject_unavailable")
                return

        stock.hold(order)
        loyalty.redeem(order)
        # Always immediate confirmation for local orders
        order.transition_status(Order.Status.CONFIRMED, actor="auto_confirm")

    def on_confirmed(self, order):
        # No digital payment for local orders — fulfill stock immediately
        # (cash/counter payment is settled at the counter, not via gateway).
        stock.fulfill(order)
        notification.send(order, "order_confirmed")

    def on_paid(self, order):
        # Local orders never receive payment webhooks; fulfill happened in
        # on_confirmed. No-op here.
        pass


@flow("pos")
class PosFlow(LocalFlow):
    """Counter POS — inherits LocalFlow."""
    pass


@flow("totem")
class TotemFlow(LocalFlow):
    """Self-service totem — inherits LocalFlow, may have self-service payment."""
    pass


# ── RemoteFlow ──


@flow("remote")
class RemoteFlow(BaseFlow):
    """Remote — payment required, active notification. Inherits BaseFlow."""
    pass


@flow("web")
class WebFlow(RemoteFlow):
    """E-commerce web storefront."""
    pass


@flow("whatsapp")
class WhatsAppFlow(RemoteFlow):
    """WhatsApp orders via ManyChat."""
    pass


@flow("manychat")
class ManychatFlow(RemoteFlow):
    """ManyChat generic channel."""
    pass


# ── MarketplaceFlow ──


@flow("marketplace")
class MarketplaceFlow(BaseFlow):
    """Marketplace — external payment, pessimistic confirmation.

    Marketplaces (iFood, Rappi) push orders that have already been "decided"
    by the customer, but the merchant can still REJECT them. `on_commit` runs
    a per-item availability check (channel listing membership + Offerman pause
    + Stockman scope) BEFORE attempting to hold stock. Any failure aborts the
    order with a typed alert; the marketplace adapter is responsible for
    actually calling reject() upstream.
    """

    def on_commit(self, order):
        customer.ensure(order)

        # Per-item availability check honoring:
        #   - channel listing membership (ListingItem published+available)
        #   - Offerman global pause (Product.is_published / is_available)
        #   - per-channel safety_margin and allowed_positions
        channel_ref = getattr(order.channel, "ref", None)
        rejected: list[tuple[str, str]] = []
        for item in order.snapshot.get("items", []):
            sku = item["sku"]
            qty = item["qty"]
            status = availability.check(sku, qty, channel_ref=channel_ref)
            if not status["ok"]:
                rejected.append((sku, status.get("error_code") or "unavailable"))

        if rejected:
            reasons = ", ".join(f"{sku}:{code}" for sku, code in rejected)
            logger.info(
                "MarketplaceFlow.on_commit: rejecting order %s — %s",
                order.ref, reasons,
            )
            _create_alert(order, "marketplace_rejected_unavailable")
            order.transition_status(Order.Status.CANCELLED, actor="auto_reject_unavailable")
            return

        stock.hold(order)

        # Defense-in-depth: hold() can still fail on a race between check and
        # create_hold (stock vanished). Compare held vs ordered SKUs.
        held_skus = {h.get("sku") for h in (order.data or {}).get("hold_ids", [])}
        ordered_skus = {item["sku"] for item in order.snapshot.get("items", [])}
        missing = ordered_skus - held_skus
        if missing:
            _create_alert(order, "marketplace_rejected_oos")
            order.transition_status(Order.Status.CANCELLED, actor="auto_reject_oos")
            stock.release(order)
            return
        # Pessimistic: wait for marketplace/operator to confirm or cancel.
        # No auto-action — order stays NEW until explicit operator intervention.

    def on_confirmed(self, order):
        # External payment — skip payment.initiate
        notification.send(order, "order_confirmed")

    def on_paid(self, order):
        # External payment — just fulfill stock + notify
        if order.status == Order.Status.CANCELLED:
            _create_alert(order, "payment_after_cancel")
            return
        stock.fulfill(order)
        notification.send(order, "payment_confirmed")


@flow("ifood")
class IFoodFlow(MarketplaceFlow):
    """iFood marketplace — inherits MarketplaceFlow."""
    pass


# ── Alert helper ──


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
        logger.exception("flows._create_alert: failed for order %s", order.ref)
