"""OrderTrackingProjection — read models for the order tracking page (Fase 2).

Translates canonical shop order tracking read models into immutable
projections consumed by storefront templates.

Never imports from ``shopman.storefront.views.*``.
"""

from __future__ import annotations

from dataclasses import dataclass

from shopman.shop.projections.types import (
    FulfillmentProjection,
    OrderItemProjection,
    TimelineEventProjection,
)
from shopman.shop.services import order_tracking

CARRIER_TRACKING_URLS = order_tracking.CARRIER_TRACKING_URLS
EVENT_LABELS = order_tracking.EVENT_LABELS
FULFILLMENT_STATUS_LABELS = order_tracking.FULFILLMENT_STATUS_LABELS


@dataclass(frozen=True)
class PickupInfoProjection:
    """Store address and hours shown when the fulfillment type is pickup."""

    address: str
    opening_hours: str
    google_maps_url: str | None


@dataclass(frozen=True)
class OrderTrackingProjection:
    """Full read model for the order tracking page."""

    order_ref: str
    status: str
    status_label: str
    status_color: str

    timeline: tuple[TimelineEventProjection, ...]
    items: tuple[OrderItemProjection, ...]

    total_display: str
    delivery_fee_display: str | None
    is_delivery: bool

    delivery_fulfillments: tuple[FulfillmentProjection, ...]
    pickup_fulfillments: tuple[FulfillmentProjection, ...]
    pickup_info: PickupInfoProjection | None

    can_cancel: bool
    is_active: bool

    # Auto-confirmation countdown (mode=auto_confirm channels)
    confirmation_countdown: bool
    confirmation_expires_at: str | None

    # ETA (when preparing)
    eta_display: str | None

    # Contact / sharing
    whatsapp_url: str
    share_text: str

    is_debug: bool


@dataclass(frozen=True)
class OrderTrackingStatusProjection:
    """Read model for the HTMX polling partial (status badge + timeline)."""

    order_ref: str
    status: str
    status_label: str
    status_color: str
    timeline: tuple[TimelineEventProjection, ...]
    is_terminal: bool
    can_cancel: bool


def build_order_tracking(order) -> OrderTrackingProjection:
    """Build the full tracking page projection for an Order."""
    from django.conf import settings

    read_model = order_tracking.build_tracking(order, is_debug=settings.DEBUG)
    return OrderTrackingProjection(
        order_ref=read_model.order_ref,
        status=read_model.status,
        status_label=read_model.status_label,
        status_color=read_model.status_color,
        timeline=read_model.timeline,
        items=read_model.items,
        total_display=read_model.total_display,
        delivery_fee_display=read_model.delivery_fee_display,
        is_delivery=read_model.is_delivery,
        delivery_fulfillments=read_model.delivery_fulfillments,
        pickup_fulfillments=read_model.pickup_fulfillments,
        pickup_info=_pickup_info_projection(read_model.pickup_info),
        can_cancel=read_model.can_cancel,
        is_active=read_model.is_active,
        confirmation_countdown=read_model.confirmation_countdown,
        confirmation_expires_at=read_model.confirmation_expires_at,
        eta_display=read_model.eta_display,
        whatsapp_url=read_model.whatsapp_url,
        share_text=read_model.share_text,
        is_debug=read_model.is_debug,
    )


def build_order_tracking_status(order) -> OrderTrackingStatusProjection:
    """Build the polling partial projection (status badge + timeline only)."""
    read_model = order_tracking.build_tracking_status(order)
    return OrderTrackingStatusProjection(
        order_ref=read_model.order_ref,
        status=read_model.status,
        status_label=read_model.status_label,
        status_color=read_model.status_color,
        timeline=read_model.timeline,
        is_terminal=read_model.is_terminal,
        can_cancel=read_model.can_cancel,
    )


def _pickup_info_projection(read_model) -> PickupInfoProjection | None:
    if read_model is None:
        return None
    return PickupInfoProjection(
        address=read_model.address,
        opening_hours=read_model.opening_hours,
        google_maps_url=read_model.google_maps_url,
    )


__all__ = [
    "OrderTrackingProjection",
    "OrderTrackingStatusProjection",
    "PickupInfoProjection",
    "build_order_tracking",
    "build_order_tracking_status",
]
