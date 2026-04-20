"""Storefront projections — typed read models for customer-facing surfaces."""

from .account import (
    CustomerProfileProjection,
    LoyaltyProjection,
    LoyaltyTransactionProjection,
    build_account,
)
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

__all__ = [
    "AllergenInfoProjection",
    "CartItemProjection",
    "CartProjection",
    "CatalogItemProjection",
    "CatalogProjection",
    "CatalogSectionProjection",
    "CheckoutProjection",
    "ConservationInfoProjection",
    "CustomerProfileProjection",
    "DiscountLineProjection",
    "LoyaltyProjection",
    "LoyaltyTransactionProjection",
    "MinimumOrderProgressProjection",
    "OrderHistoryProjection",
    "OrderTrackingProjection",
    "OrderTrackingStatusProjection",
    "PaymentProjection",
    "PaymentStatusProjection",
    "PickupInfoProjection",
    "ProductDetailProjection",
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
