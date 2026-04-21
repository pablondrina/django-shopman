"""OrderTrackingProjection — read models for the order tracking page (Fase 2).

Translates an Order + its events/fulfillments into two immutable projections:

``build_order_tracking``        → full tracking page.
``build_order_tracking_status`` → HTMX polling partial (status badge + timeline).

Mirrors the logic in ``shopman.storefront.views.tracking._build_tracking_context``
but shaped into frozen dataclasses and using Penguin UI semantic colour tokens
instead of raw Tailwind classes.

Never imports from ``shopman.storefront.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.utils import timezone
from shopman.utils.monetary import format_money

from shopman.shop.projections.types import (
    ORDER_STATUS_COLORS,
    ORDER_STATUS_LABELS_PT,
    FulfillmentProjection,
    OrderItemProjection,
    TimelineEventProjection,
)

if TYPE_CHECKING:
    from shopman.orderman.models import Order

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset({"completed", "cancelled", "returned"})
_CANCELLABLE_STATUSES = frozenset({"new", "confirmed"})

EVENT_LABELS: dict[str, str | None] = {
    "created": "Pedido criado",
    "status_changed": None,
    "payment.captured": "Pagamento confirmado",
    "payment.refunded": "Pagamento estornado",
    "return_initiated": "Devolução solicitada",
    "refund_processed": "Reembolso processado",
    "fiscal_cancelled": "Nota fiscal cancelada",
    "fulfillment.dispatched": "Saiu para entrega",
    "fulfillment.delivered": "Pedido entregue",
}

FULFILLMENT_STATUS_LABELS: dict[str, str] = {
    "pending": "Aguardando",
    "in_progress": "Em separação",
    "dispatched": "Saiu para entrega",
    "delivered": "Entregue",
    "cancelled": "Cancelado",
}


# ──────────────────────────────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PickupInfoProjection:
    """Store address and hours shown when the fulfillment type is pickup."""

    address: str
    opening_hours: str


@dataclass(frozen=True)
class OrderTrackingProjection:
    """Full read model for the order tracking page."""

    order_ref: str
    status: str
    status_label: str
    status_color: str     # Penguin UI token classes

    timeline: tuple[TimelineEventProjection, ...]
    items: tuple[OrderItemProjection, ...]

    total_display: str
    delivery_fee_display: str | None
    is_delivery: bool

    delivery_fulfillments: tuple[FulfillmentProjection, ...]
    pickup_fulfillments: tuple[FulfillmentProjection, ...]
    pickup_info: PickupInfoProjection | None

    can_cancel: bool
    is_active: bool          # not in terminal status

    # Auto-confirmation countdown (mode=auto_confirm channels)
    confirmation_countdown: bool
    confirmation_expires_at: str | None  # ISO datetime or None

    # ETA (when preparing)
    eta_display: str | None

    # Contact / sharing
    whatsapp_url: str
    share_text: str

    is_debug: bool


@dataclass(frozen=True)
class OrderTrackingStatusProjection:
    """Read model for the HTMX polling partial (status badge + timeline).

    Views return HTTP 286 when ``is_terminal`` to stop HTMX polling.
    """

    order_ref: str
    status: str
    status_label: str
    status_color: str
    timeline: tuple[TimelineEventProjection, ...]
    is_terminal: bool
    can_cancel: bool


# ──────────────────────────────────────────────────────────────────────
# Builders
# ──────────────────────────────────────────────────────────────────────


def build_order_tracking(order: Order) -> OrderTrackingProjection:
    """Build the full tracking page projection for an Order."""
    from django.conf import settings

    status_label, status_color = _status_display(order)
    timeline = _build_timeline(order)
    items = _build_items(order)
    delivery_fulfillments, pickup_fulfillments = _build_fulfillments(order)
    pickup_info = _pickup_info() if pickup_fulfillments else None

    order_data = order.data or {}
    delivery_fee_q = order_data.get("delivery_fee_q")
    delivery_fee_display: str | None = None
    if delivery_fee_q is not None:
        delivery_fee_display = (
            "Grátis" if delivery_fee_q == 0 else f"R$ {format_money(delivery_fee_q)}"
        )

    fulfillment_type = order_data.get("fulfillment_type") or order_data.get("delivery_method", "")
    is_delivery = fulfillment_type == "delivery"

    can_cancel = _can_cancel(order)
    is_active = order.status not in _TERMINAL_STATUSES

    confirmation_countdown, confirmation_expires_at = _confirmation_info(order)
    eta_display = _eta_display(order)

    whatsapp_url, share_text = _contact_and_share(order)

    return OrderTrackingProjection(
        order_ref=order.ref,
        status=order.status,
        status_label=status_label,
        status_color=status_color,
        timeline=timeline,
        items=items,
        total_display=f"R$ {format_money(order.total_q)}",
        delivery_fee_display=delivery_fee_display,
        is_delivery=is_delivery,
        delivery_fulfillments=delivery_fulfillments,
        pickup_fulfillments=pickup_fulfillments,
        pickup_info=pickup_info,
        can_cancel=can_cancel,
        is_active=is_active,
        confirmation_countdown=confirmation_countdown,
        confirmation_expires_at=confirmation_expires_at,
        eta_display=eta_display,
        whatsapp_url=whatsapp_url,
        share_text=share_text,
        is_debug=settings.DEBUG,
    )


def build_order_tracking_status(order: Order) -> OrderTrackingStatusProjection:
    """Build the polling partial projection (status badge + timeline only)."""
    status_label, status_color = _status_display(order)
    timeline = _build_timeline(order)

    return OrderTrackingStatusProjection(
        order_ref=order.ref,
        status=order.status,
        status_label=status_label,
        status_color=status_color,
        timeline=timeline,
        is_terminal=order.status in _TERMINAL_STATUSES,
        can_cancel=_can_cancel(order),
    )


# ──────────────────────────────────────────────────────────────────────
# Internals
# ──────────────────────────────────────────────────────────────────────


def _status_display(order: Order) -> tuple[str, str]:
    """Return (status_label, status_color) — contextual for ready/completed."""
    order_data = order.data or {}
    fulfillment_type = order_data.get("fulfillment_type") or order_data.get("delivery_method", "")
    is_delivery = fulfillment_type == "delivery"

    label = ORDER_STATUS_LABELS_PT.get(order.status, order.status)
    if order.status == "ready":
        label = "Aguardando motoboy" if is_delivery else "Pronto para retirada"
    elif order.status == "completed":
        label = "Entregue" if is_delivery else "Concluído"

    color = ORDER_STATUS_COLORS.get(order.status, "bg-surface-alt text-on-surface/60 border border-outline")
    return label, color


def _fmt_timestamp(dt) -> str:
    """Format a datetime as 'DD/MM às HH:MM' for the timeline."""
    try:
        local = timezone.localtime(dt)
        return local.strftime("%d/%m às %H:%M")
    except Exception:
        return str(dt)


def _build_timeline(order: Order) -> tuple[TimelineEventProjection, ...]:
    """Build chronological timeline from order events + fulfillment dispatches."""
    raw: list[tuple] = []  # (datetime, label, event_type)

    for event in order.events.order_by("seq"):
        payload = event.payload or {}
        status_key = payload.get("new_status", "")

        if event.type == "status_changed" and status_key:
            label = ORDER_STATUS_LABELS_PT.get(status_key, status_key)
        else:
            label = EVENT_LABELS.get(event.type)
            if label is None:
                label = event.type.replace(".", " ").replace("_", " ").title()

        raw.append((event.created_at, label, event.type))

    for ful in order.fulfillments.all():
        if ful.dispatched_at:
            raw.append((ful.dispatched_at, "Enviado", "fulfillment.dispatched"))
        if ful.delivered_at:
            raw.append((ful.delivered_at, "Entregue", "fulfillment.delivered"))

    raw.sort(key=lambda x: x[0])

    return tuple(
        TimelineEventProjection(
            label=lbl,
            event_type=evt,
            timestamp_display=_fmt_timestamp(ts),
        )
        for ts, lbl, evt in raw
    )


def _build_items(order: Order) -> tuple[OrderItemProjection, ...]:
    return tuple(
        OrderItemProjection(
            sku=item.sku,
            name=item.name or item.sku,
            qty=int(item.qty),
            unit_price_display=f"R$ {format_money(item.unit_price_q)}",
            total_display=f"R$ {format_money(item.line_total_q)}",
        )
        for item in order.items.all()
    )


def _build_fulfillments(
    order: Order,
) -> tuple[tuple[FulfillmentProjection, ...], tuple[FulfillmentProjection, ...]]:
    """Return (delivery_fulfillments, pickup_fulfillments)."""
    from shopman.storefront.views._helpers import _carrier_tracking_url

    delivery: list[FulfillmentProjection] = []
    pickup: list[FulfillmentProjection] = []

    for ful in order.fulfillments.all():
        tracking_url = ful.tracking_url or _carrier_tracking_url(ful.carrier, ful.tracking_code)
        proj = FulfillmentProjection(
            status=ful.status,
            status_label=FULFILLMENT_STATUS_LABELS.get(ful.status, ful.status),
            tracking_code=ful.tracking_code or None,
            tracking_url=tracking_url,
            carrier=ful.carrier or None,
            dispatched_at_display=_fmt_timestamp(ful.dispatched_at) if ful.dispatched_at else None,
            delivered_at_display=_fmt_timestamp(ful.delivered_at) if ful.delivered_at else None,
        )
        if ful.carrier or ful.tracking_code:
            delivery.append(proj)
        else:
            pickup.append(proj)

    return tuple(delivery), tuple(pickup)


def _pickup_info() -> PickupInfoProjection | None:
    """Load store address and opening hours for pickup fulfillments."""
    try:
        from shopman.shop.models import Shop
        from shopman.storefront.views._helpers import _format_opening_hours

        shop = Shop.load()
        if not shop:
            return None

        hours_list = _format_opening_hours()
        hours_str = "; ".join(f"{h['label']}: {h['hours']}" for h in hours_list)
        return PickupInfoProjection(
            address=shop.formatted_address or "",
            opening_hours=hours_str,
        )
    except Exception:
        logger.exception("order_tracking_projection_pickup_info_failed")
        return None


def _can_cancel(order: Order) -> bool:
    """True if the order can be customer-cancelled."""
    try:
        from shopman.shop.services import payment as payment_svc

        return (
            order.status in _CANCELLABLE_STATUSES
            and payment_svc.get_payment_status(order) != "captured"
        )
    except Exception:
        return False


def _confirmation_info(order: Order) -> tuple[bool, str | None]:
    """Return (show_countdown, expires_at_iso_or_None)."""
    if order.status != "new":
        return False, None
    try:
        from datetime import timedelta

        from shopman.shop.config import ChannelConfig
        from shopman.shop.models import Channel

        channel = Channel.objects.filter(ref=order.channel_ref).first()
        if not channel:
            return False, None

        cfg = ChannelConfig.for_channel(channel).confirmation
        if cfg.mode == "auto_confirm":
            expires_at = order.created_at + timedelta(minutes=cfg.timeout_minutes)
            return True, expires_at.isoformat()
    except Exception:
        logger.exception("order_tracking_projection_confirmation_failed")
    return False, None


def _eta_display(order: Order) -> str | None:
    """ETA display string when order is being prepared."""
    if order.status != "preparing":
        return None
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        prep_minutes = getattr(shop, "prep_time_minutes", None) or 30
        eta = timezone.localtime(order.created_at) + timezone.timedelta(minutes=prep_minutes)
        return eta.strftime("%H:%M")
    except Exception:
        return None


def _contact_and_share(order: Order) -> tuple[str, str]:
    """Return (whatsapp_url, share_text)."""
    whatsapp_url = ""
    shop_name = "loja"
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        if shop:
            shop_name = shop.name or "loja"
            for link in (shop.social_links or []):
                if "wa.me" in link or "whatsapp.com" in link:
                    whatsapp_url = link
                    break
            if not whatsapp_url and shop.phone:
                digits = "".join(c for c in shop.phone if c.isdigit())
                whatsapp_url = f"https://wa.me/{digits}"
    except Exception:
        logger.exception("order_tracking_projection_contact_failed")

    share_text = f"Meu pedido {order.ref} na {shop_name}"
    return whatsapp_url, share_text


__all__ = [
    "OrderTrackingProjection",
    "OrderTrackingStatusProjection",
    "PickupInfoProjection",
    "build_order_tracking",
    "build_order_tracking_status",
]
