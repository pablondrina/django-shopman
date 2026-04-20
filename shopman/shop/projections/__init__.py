"""Projections — shared typed read models.

Shared types (Availability, OrderItem, etc.) live here as canonical home.
Surface-specific projections live in storefront/ and backstage/.
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
