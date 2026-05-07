"""Order tracking projections consumed by storefront templates.

The canonical projection is built in ``shopman.shop.services.order_tracking``.
There is no separate Storefront DTO layer here: templates consume the same
projection that the tracking service builds.
"""

from __future__ import annotations

from shopman.shop.services.order_tracking import (
    CARRIER_TRACKING_URLS,
    EVENT_LABELS,
    FULFILLMENT_STATUS_LABELS,
    OrderTrackingProjection,
    OrderTrackingPromiseProjection,
    OrderTrackingStatusProjection,
    PickupInfoProjection,
    build_tracking,
    build_tracking_status,
)


def build_order_tracking(order) -> OrderTrackingProjection:
    """Build the full tracking page projection for an Order."""
    from django.conf import settings

    return build_tracking(order, is_debug=settings.DEBUG)


def build_order_tracking_status(order) -> OrderTrackingStatusProjection:
    """Build the polling partial projection for an Order."""
    return build_tracking_status(order)


__all__ = [
    "CARRIER_TRACKING_URLS",
    "EVENT_LABELS",
    "FULFILLMENT_STATUS_LABELS",
    "OrderTrackingProjection",
    "OrderTrackingPromiseProjection",
    "OrderTrackingStatusProjection",
    "PickupInfoProjection",
    "build_order_tracking",
    "build_order_tracking_status",
]
