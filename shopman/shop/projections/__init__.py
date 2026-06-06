"""Projections — shared typed read models.

Shared types (Availability, OrderItem, etc.) live here as canonical home.
Surface-specific projections live in storefront/ and backstage/.
"""

from .types import (  # noqa: F401
    ORDER_STATUS_COLORS,
    ORDER_STATUS_LABELS_PT,
    PAYMENT_METHOD_LABELS_PT,
    AddressAutocompleteProjection,
    Availability,
    CategoryProjection,
    FoodPrefProjection,
    HappyHourProjection,
    NotificationPrefProjection,
    OrderItemProjection,
    PickupSlotProjection,
    SavedAddressProjection,
    TimelineEventProjection,
)
