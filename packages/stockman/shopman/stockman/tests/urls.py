from __future__ import annotations

from django.urls import include, path

urlpatterns = [
    path("api/stocking/", include("shopman.stockman.api.urls")),
]
