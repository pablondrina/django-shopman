"""Storefront Presentation — appearance built from shop.projections data.

Each module here consumes a data Projection (``shopman.shop.projections``) plus
the copy catalog and produces the display shape its templates / REST surface
consume. No policy, no Core, no ``shop.services`` (write-side) — appearance only.
"""

from .account import (
    CustomerProfileProjection,
    LoyaltyProjection,
    LoyaltyTransactionProjection,
    build_account,
    order_history_for_customer,
    order_history_for_phone,
)
from .order_history import (
    OrderHistoryProjection,
    build_order_history,
)
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
    "CustomerProfileProjection",
    "LoyaltyProjection",
    "LoyaltyTransactionProjection",
    "OrderHistoryProjection",
    "OrderTrackingCopyProjection",
    "OrderTrackingProjection",
    "OrderTrackingPromiseProjection",
    "OrderTrackingPromiseRowProjection",
    "OrderTrackingStatusProjection",
    "PaymentProjection",
    "PaymentPromiseProjection",
    "PaymentStatusProjection",
    "PickupInfoProjection",
    "build_account",
    "build_order_history",
    "build_order_tracking",
    "build_order_tracking_status",
    "build_payment",
    "build_payment_status",
    "order_history_for_customer",
    "order_history_for_phone",
    "present_payment",
    "present_payment_status",
    "present_tracking",
    "present_tracking_status",
    "promise_has_pending_payment_action",
]
