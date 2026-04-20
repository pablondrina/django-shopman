"""Projections — shared typed read models.

Shared types (Availability, OrderItem, etc.) live here as canonical home.
Surface-specific projections now live in storefront/ and backstage/.

NOTE: Transitional re-exports kept for dead code in shop/web/views/ and
shop/tests/web/. Delete those directories to remove this block.
"""

from .types import (  # noqa: F401
    ORDER_STATUS_COLORS,
    ORDER_STATUS_LABELS_PT,
    PAYMENT_METHOD_LABELS_PT,
    Availability,
    CategoryProjection,
    ComponentProjection,
    FoodPrefProjection,
    FulfillmentProjection,
    HappyHourProjection,
    NotificationPrefProjection,
    OrderItemProjection,
    OrderSummaryProjection,
    PaymentMethodOptionProjection,
    PickupSlotProjection,
    SavedAddressProjection,
    TimelineEventProjection,
)

# ── Transitional re-exports (remove after deleting shop/web/ + shop/tests/web/) ──

from shopman.storefront.projections import (  # noqa: E402, F401
    build_cart,
    build_catalog,
    build_checkout,
    build_order_history,
    build_order_tracking,
    build_order_tracking_status,
    build_payment,
    build_payment_status,
    build_product_detail,
)
