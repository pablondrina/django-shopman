"""Projections — shared typed read models.

Shared types (Availability, OrderItem, etc.) live here as canonical home.
Surface-specific projections live in storefront/ and backstage/.
"""

from .types import (  # noqa: F401
    ORDER_STATUS_TONES,
    AddressAutocompleteProjection,
    Availability,
    CategoryProjection,
    HappyHourProjection,
    OrderItemProjection,
    PickupSlotProjection,
    SavedAddressProjection,
    TimelineEventProjection,
    Tone,
)
