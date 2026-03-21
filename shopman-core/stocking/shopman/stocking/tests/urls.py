from __future__ import annotations

from django.urls import include, path

urlpatterns = [
    path("api/stocking/", include("shopman.stocking.api.urls")),
]
