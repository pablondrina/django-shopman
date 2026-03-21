from __future__ import annotations

from django.urls import include, path

urlpatterns = [
    path("api/attending/", include("shopman.attending.api.urls")),
]
