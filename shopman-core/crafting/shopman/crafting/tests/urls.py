"""
URL configuration for Craftsman tests.
"""

from django.urls import include, path

urlpatterns = [
    path("api/crafting/", include("shopman.crafting.api.urls")),
]
