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
    get_channel_listing_ref,
)
from .checkout import CheckoutProjection, build_checkout
from .fomo import FomoBadge, badges_for_product
from .home import (
    AuthCopyProjection,
    CopyEntryProjection,
    HomeHeroCopyProjection,
    HomeProjection,
    HomeSectionsCopyProjection,
    LastOrderItemProjection,
    OmotenashiProjection,
    OpeningHoursEntry,
    ShopStatusProjection,
    build_home,
)
from .order_confirmation import OrderConfirmationProjection, build_order_confirmation
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
from .product_detail import (
    AllergenInfoProjection,
    ConservationInfoProjection,
    ProductDetailProjection,
    build_product_detail,
)
from .reorder import (
    ReorderConflictCopyProjection,
    ReorderConflictItemProjection,
    ReorderConflictProjection,
    build_reorder_conflict,
)
from .shop import ShopProjection, SocialLinkProjection, build_shop_projection

__all__ = [
    "AllergenInfoProjection",
    "AuthCopyProjection",
    "CartItemProjection",
    "CartProjection",
    "CatalogItemProjection",
    "CatalogProjection",
    "CatalogSectionProjection",
    "CheckoutProjection",
    "ConservationInfoProjection",
    "CopyEntryProjection",
    "CustomerProfileProjection",
    "DiscountLineProjection",
    "FomoBadge",
    "HomeHeroCopyProjection",
    "HomeProjection",
    "HomeSectionsCopyProjection",
    "LastOrderItemProjection",
    "LoyaltyProjection",
    "LoyaltyTransactionProjection",
    "MinimumOrderProgressProjection",
    "OmotenashiProjection",
    "OpeningHoursEntry",
    "OrderConfirmationProjection",
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
    "ProductDetailProjection",
    "ReorderConflictCopyProjection",
    "ReorderConflictItemProjection",
    "ReorderConflictProjection",
    "ShopProjection",
    "ShopStatusProjection",
    "SocialLinkProjection",
    "UpsellSuggestionProjection",
    "badges_for_product",
    "build_account",
    "build_cart",
    "build_catalog",
    "build_catalog_items_for_skus",
    "get_channel_listing_ref",
    "build_checkout",
    "build_home",
    "build_order_confirmation",
    "build_order_history",
    "build_order_tracking",
    "build_order_tracking_status",
    "build_payment",
    "build_payment_status",
    "build_product_detail",
    "build_reorder_conflict",
    "build_shop_projection",
    "order_history_for_customer",
    "order_history_for_phone",
    "present_payment",
    "present_payment_status",
    "present_tracking",
    "present_tracking_status",
    "promise_has_pending_payment_action",
]
