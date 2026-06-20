"""Shopman API URL configuration."""

from __future__ import annotations

from django.urls import path

from . import views
from .account import (
    AccountDeleteView,
    AccountDeviceDetailView,
    AccountDeviceListView,
    AccountExportView,
    AccountStepUpView,
    AccountSummaryView,
    ActiveOrderCountView,
    AddressDetailView,
    AddressListView,
    FavoriteDetailView,
    FavoriteListView,
    FoodPreferenceToggleView,
    NotificationPreferenceToggleView,
    OrderHistoryView,
    ProfileView,
)
from .auth import (
    AccessLinkExchangeView,
    DeviceCheckView,
    LogoutView,
    RequestCodeView,
    SessionView,
    TrustDeviceView,
    VerifyCodeView,
)
from .availability import AvailabilityView, StockAlertSubscribeView
from .catalog import CollectionListView, ProductDetailView, ProductListView
from .conversation import OrderConversationView
from .geocode import ReverseGeocodeView
from .payment import OrderPaymentMockConfirmView, OrderPaymentStatusView, OrderPaymentView
from .surface import (
    CartCouponView,
    CartSkuQtyView,
    CheckoutDraftView,
    CheckoutLoyaltyView,
    OrderReorderView,
    StorefrontCartView,
    StorefrontCheckoutView,
    StorefrontHomeView,
    StorefrontMenuView,
    StorefrontProductView,
)
from .tracking import OrderCancelView, OrderRateView, OrderTrackingView

urlpatterns = [
    # Storefront projections for API-first clients
    path("storefront/home/", StorefrontHomeView.as_view(), name="api-storefront-home"),
    path("storefront/menu/", StorefrontMenuView.as_view(), name="api-storefront-menu"),
    path("storefront/menu/<slug:collection>/", StorefrontMenuView.as_view(), name="api-storefront-menu-collection"),
    path("storefront/products/<str:sku>/", StorefrontProductView.as_view(), name="api-storefront-product"),
    path("storefront/cart/", StorefrontCartView.as_view(), name="api-storefront-cart"),
    path("storefront/checkout/", StorefrontCheckoutView.as_view(), name="api-storefront-checkout"),
    # Auth
    path("auth/session/", SessionView.as_view(), name="api-auth-session"),
    path("auth/access/", AccessLinkExchangeView.as_view(), name="api-auth-access"),
    path("auth/device-check/", DeviceCheckView.as_view(), name="api-auth-device-check"),
    path("auth/request-code/", RequestCodeView.as_view(), name="api-auth-request-code"),
    path("auth/verify-code/", VerifyCodeView.as_view(), name="api-auth-verify-code"),
    path("auth/trust-device/", TrustDeviceView.as_view(), name="api-auth-trust-device"),
    path("auth/logout/", LogoutView.as_view(), name="api-auth-logout"),
    # Cart
    path("cart/skus/<str:sku>/", CartSkuQtyView.as_view(), name="api-cart-sku-qty"),
    path("cart/coupon/", CartCouponView.as_view(), name="api-cart-coupon"),
    # Checkout
    path("checkout/", views.CheckoutView.as_view(), name="api-checkout"),
    path("checkout/draft/", CheckoutDraftView.as_view(), name="api-checkout-draft"),
    path("checkout/loyalty/", CheckoutLoyaltyView.as_view(), name="api-checkout-loyalty"),
    # Availability
    path("availability/<str:sku>/", AvailabilityView.as_view(), name="api-availability"),
    path("availability/<str:sku>/notify/", StockAlertSubscribeView.as_view(), name="api-availability-notify"),
    # Catalog
    path("catalog/products/", ProductListView.as_view(), name="api-catalog-products"),
    path("catalog/products/<str:sku>/", ProductDetailView.as_view(), name="api-catalog-product-detail"),
    path("catalog/collections/", CollectionListView.as_view(), name="api-catalog-collections"),
    # Tracking
    path("tracking/<str:ref>/", OrderTrackingView.as_view(), name="api-tracking"),
    path("orders/<str:ref>/cancel/", OrderCancelView.as_view(), name="api-order-cancel"),
    path("orders/<str:ref>/rate/", OrderRateView.as_view(), name="api-order-rate"),
    path("orders/<str:ref>/conversation/", OrderConversationView.as_view(), name="api-order-conversation"),
    path("payment/<str:ref>/", OrderPaymentView.as_view(), name="api-payment"),
    path("payment/<str:ref>/status/", OrderPaymentStatusView.as_view(), name="api-payment-status"),
    path("payment/<str:ref>/mock-confirm/", OrderPaymentMockConfirmView.as_view(), name="api-payment-mock-confirm"),
    path("orders/<str:ref>/reorder/", OrderReorderView.as_view(), name="api-order-reorder"),
    # Account
    path("account/summary/", AccountSummaryView.as_view(), name="api-account-summary"),
    path("account/profile/", ProfileView.as_view(), name="api-account-profile"),
    path("account/addresses/", AddressListView.as_view(), name="api-account-addresses"),
    path("account/addresses/<int:pk>/", AddressDetailView.as_view(), name="api-account-address-detail"),
    path("account/favorites/", FavoriteListView.as_view(), name="api-account-favorites"),
    path("account/favorites/<str:sku>/", FavoriteDetailView.as_view(), name="api-account-favorite-detail"),
    path("account/orders/", OrderHistoryView.as_view(), name="api-account-orders"),
    path("account/orders/active/", ActiveOrderCountView.as_view(), name="api-account-active-orders"),
    path("account/preferences/food/", FoodPreferenceToggleView.as_view(), name="api-account-food-preferences"),
    path(
        "account/preferences/notifications/",
        NotificationPreferenceToggleView.as_view(),
        name="api-account-notification-preferences",
    ),
    path("account/devices/", AccountDeviceListView.as_view(), name="api-account-devices"),
    path("account/devices/<uuid:device_id>/", AccountDeviceDetailView.as_view(), name="api-account-device-detail"),
    path("account/step-up/", AccountStepUpView.as_view(), name="api-account-step-up"),
    path("account/export/", AccountExportView.as_view(), name="api-account-export"),
    path("account/delete/", AccountDeleteView.as_view(), name="api-account-delete"),
    # Geocoding (server-side — key stays on the server)
    path("geocode/reverse/", ReverseGeocodeView.as_view(), name="api-geocode-reverse"),
]
