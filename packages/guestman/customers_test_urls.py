"""Minimal URL config for Customers tests."""

from django.urls import include, path

urlpatterns = [
    path("api/customers/", include("shopman.guestman.api.urls")),
]
