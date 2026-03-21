"""Minimal URL config for Attending tests."""

from django.urls import include, path

urlpatterns = [
    path("api/attending/", include("shopman.attending.api.urls")),
]
