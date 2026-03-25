from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path("cart/", views.CartView.as_view(), name="api-cart"),
    path("cart/items/", views.CartAddItemView.as_view(), name="api-cart-add"),
    path("cart/items/<str:line_id>/", views.CartItemView.as_view(), name="api-cart-item"),
    path("checkout/", views.CheckoutView.as_view(), name="api-checkout"),
]
