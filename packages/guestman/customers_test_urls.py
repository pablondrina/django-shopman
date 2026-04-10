"""Minimal URL config for Guestman tests."""

from django.urls import include, path

urlpatterns = [
    path("api/customers/", include("shopman.guestman.api.urls")),
]
