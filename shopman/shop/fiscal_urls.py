"""URLs fiscais — DANFE NFC-e (cupom de operador, imprimível)."""

from __future__ import annotations

from django.urls import path

from shopman.shop.views.fiscal_danfe import DanfeView

urlpatterns = [
    path("fiscal/danfe/<str:ref>/", DanfeView.as_view(), name="fiscal-danfe"),
]
