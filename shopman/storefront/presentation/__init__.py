"""Storefront Presentation — appearance built from shop.projections data.

Each module here consumes a data Projection (``shopman.shop.projections``) plus
the copy catalog and produces the display shape its templates / REST surface
consume. No policy, no Core, no ``shop.services`` (write-side) — appearance only.
"""

from .order_tracking import (
    OrderTrackingCopyProjection,
    OrderTrackingProjection,
    OrderTrackingPromiseProjection,
    OrderTrackingPromiseRowProjection,
    OrderTrackingStatusProjection,
    PickupInfoProjection,
    build_order_tracking,
    build_order_tracking_status,
    present_tracking,
    present_tracking_status,
)
from .payment import (
    PaymentProjection,
    PaymentPromiseProjection,
    PaymentStatusProjection,
    build_payment,
    build_payment_status,
    present_payment,
    present_payment_status,
    promise_has_pending_payment_action,
)

__all__ = [
    "OrderTrackingCopyProjection",
    "OrderTrackingProjection",
    "OrderTrackingPromiseProjection",
    "OrderTrackingPromiseRowProjection",
    "OrderTrackingStatusProjection",
    "PaymentProjection",
    "PaymentPromiseProjection",
    "PaymentStatusProjection",
    "PickupInfoProjection",
    "build_order_tracking",
    "build_order_tracking_status",
    "build_payment",
    "build_payment_status",
    "present_payment",
    "present_payment_status",
    "present_tracking",
    "present_tracking_status",
    "promise_has_pending_payment_action",
]
