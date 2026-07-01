"""Menuboard URLs — página pública, dados JSON e stream SSE por superfície."""

from __future__ import annotations

from django.urls import path
from django_eventstream.views import events as eventstream_view

from shopman.shop.views.menuboard import MenuboardDataView, MenuboardPageView

urlpatterns = [
    path("menuboard/<slug:ref>/", MenuboardPageView.as_view(), name="menuboard"),
    path("menuboard/<slug:ref>/data/", MenuboardDataView.as_view(), name="menuboard-data"),
    # Reusa o canal público ``stock-{ref}`` que o motor de disponibilidade já emite
    # ao pausar/reprecificar itens (ver shop/handlers/_sse_emitters.py).
    path(
        "menuboard/<slug:ref>/events/",
        eventstream_view,
        {"format-channels": ["stock-{ref}"]},
        name="menuboard-events",
    ),
]
