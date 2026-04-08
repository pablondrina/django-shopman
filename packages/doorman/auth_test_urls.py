"""Minimal URL config for Auth tests."""

from django.urls import include, path

urlpatterns = [
    path("auth/", include("shopman.doorman.urls")),
]
