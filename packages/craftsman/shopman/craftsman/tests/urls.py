"""
URL configuration for Craftsman tests.
"""

from django.urls import include, path

urlpatterns = [
    path("api/craftsman/", include("shopman.craftsman.api.urls")),
]
