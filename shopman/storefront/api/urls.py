"""Shopman API URL configuration."""

from __future__ import annotations

from django.urls import path

from . import views
from .account import AddressListView, OrderHistoryView, ProfileView
from .availability import AvailabilityView
from .catalog import CollectionListView, ProductDetailView, ProductListView
from .geocode import ReverseGeocodeView
from .surface import (
    CartSkuQtyView,
    StorefrontCartView,
    StorefrontMenuView,
    StorefrontProductView,
)
from .tracking import OrderTrackingView

urlpatterns = [
    # Storefront projections for API-first clients
    path("storefront/menu/", StorefrontMenuView.as_view(), name="api-storefront-menu"),
    path("storefront/menu/<slug:collection>/", StorefrontMenuView.as_view(), name="api-storefront-menu-collection"),
    path("storefront/products/<str:sku>/", StorefrontProductView.as_view(), name="api-storefront-product"),
    path("storefront/cart/", StorefrontCartView.as_view(), name="api-storefront-cart"),
    # Cart
    path("cart/", views.CartView.as_view(), name="api-cart"),
    path("cart/skus/<str:sku>/", CartSkuQtyView.as_view(), name="api-cart-sku-qty"),
    path("cart/items/", views.CartAddItemView.as_view(), name="api-cart-add"),
    path("cart/items/<str:line_id>/", views.CartItemView.as_view(), name="api-cart-item"),
    # Checkout
    path("checkout/", views.CheckoutView.as_view(), name="api-checkout"),
    # Availability
    path("availability/<str:sku>/", AvailabilityView.as_view(), name="api-availability"),
    # Catalog
    path("catalog/products/", ProductListView.as_view(), name="api-catalog-products"),
    path("catalog/products/<str:sku>/", ProductDetailView.as_view(), name="api-catalog-product-detail"),
    path("catalog/collections/", CollectionListView.as_view(), name="api-catalog-collections"),
    # Tracking
    path("tracking/<str:ref>/", OrderTrackingView.as_view(), name="api-tracking"),
    # Account
    path("account/profile/", ProfileView.as_view(), name="api-account-profile"),
    path("account/addresses/", AddressListView.as_view(), name="api-account-addresses"),
    path("account/orders/", OrderHistoryView.as_view(), name="api-account-orders"),
    # Geocoding (server-side — key stays on the server)
    path("geocode/reverse", ReverseGeocodeView.as_view(), name="api-geocode-reverse"),
]
