"""Projections — typed read models.

Projections translate domain state into what the UI (and later, the API) needs
to consume. Views call a builder, pass the result to the template. Templates
consume a stable interface instead of domain model internals.

Rules:
- Projections are read-only and immutable (frozen dataclasses)
- Never expose PKs, querysets, or model instances
- Monetary values are dual: raw (`_q` in cents) + display (pre-formatted string)
- Availability is a canonical enum, not a bool
"""

from .cart import (
    CartItemProjection,
    CartProjection,
    DiscountLineProjection,
    MinimumOrderProgressProjection,
    UpsellSuggestionProjection,
    build_cart,
)
from .catalog import (
    CatalogItemProjection,
    CatalogProjection,
    CatalogSectionProjection,
    build_catalog,
    build_catalog_items_for_skus,
)
from .account import (
    CustomerProfileProjection,
    LoyaltyProjection,
    LoyaltyTransactionProjection,
    build_account,
)
from .checkout import CheckoutProjection, build_checkout
from .order_history import OrderHistoryProjection, build_order_history
from .order_tracking import (
    OrderTrackingProjection,
    OrderTrackingStatusProjection,
    PickupInfoProjection,
    build_order_tracking,
    build_order_tracking_status,
)
from .payment import (
    PaymentProjection,
    PaymentStatusProjection,
    build_payment,
    build_payment_status,
)
from .product_detail import (
    AllergenInfoProjection,
    ConservationInfoProjection,
    ProductDetailProjection,
    build_product_detail,
)
from .types import (
    Availability,
    CategoryProjection,
    ComponentProjection,
    FoodPrefProjection,
    FulfillmentProjection,
    HappyHourProjection,
    NotificationPrefProjection,
    ORDER_STATUS_COLORS,
    ORDER_STATUS_LABELS_PT,
    OrderItemProjection,
    OrderSummaryProjection,
    PAYMENT_METHOD_LABELS_PT,
    PaymentMethodOptionProjection,
    PickupSlotProjection,
    SavedAddressProjection,
    TimelineEventProjection,
)

__all__ = [
    "AllergenInfoProjection",
    "Availability",
    "CartItemProjection",
    "CartProjection",
    "CatalogItemProjection",
    "CatalogProjection",
    "CatalogSectionProjection",
    "CategoryProjection",
    "CheckoutProjection",
    "ComponentProjection",
    "ConservationInfoProjection",
    "CustomerProfileProjection",
    "DiscountLineProjection",
    "FoodPrefProjection",
    "FulfillmentProjection",
    "HappyHourProjection",
    "LoyaltyProjection",
    "LoyaltyTransactionProjection",
    "MinimumOrderProgressProjection",
    "NotificationPrefProjection",
    "ORDER_STATUS_COLORS",
    "ORDER_STATUS_LABELS_PT",
    "OrderHistoryProjection",
    "OrderItemProjection",
    "OrderSummaryProjection",
    "OrderTrackingProjection",
    "OrderTrackingStatusProjection",
    "PAYMENT_METHOD_LABELS_PT",
    "PaymentMethodOptionProjection",
    "PaymentProjection",
    "PaymentStatusProjection",
    "PickupInfoProjection",
    "PickupSlotProjection",
    "ProductDetailProjection",
    "SavedAddressProjection",
    "TimelineEventProjection",
    "UpsellSuggestionProjection",
    "build_account",
    "build_cart",
    "build_catalog",
    "build_catalog_items_for_skus",
    "build_checkout",
    "build_order_history",
    "build_order_tracking",
    "build_order_tracking_status",
    "build_payment",
    "build_payment_status",
    "build_product_detail",
]
