"""Minimal URL config for Gating tests."""

from django.urls import include, path

urlpatterns = [
    path("gating/", include("shopman.gating.urls")),
]
