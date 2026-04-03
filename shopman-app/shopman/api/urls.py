"""Shopman API URL configuration."""

from __future__ import annotations

from django.urls import path

from . import views
from .account import AddressListView, OrderHistoryView, ProfileView
from .catalog import CollectionListView, ProductDetailView, ProductListView
from .tracking import OrderTrackingView

urlpatterns = [
    # Cart
    path("cart/", views.CartView.as_view(), name="api-cart"),
    path("cart/items/", views.CartAddItemView.as_view(), name="api-cart-add"),
    path("cart/items/<str:line_id>/", views.CartItemView.as_view(), name="api-cart-item"),
    # Checkout
    path("checkout/", views.CheckoutView.as_view(), name="api-checkout"),
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
]
