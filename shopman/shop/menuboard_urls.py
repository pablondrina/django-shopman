"""Superfícies públicas — menuboard (display) e feed (Google/Meta) por ref.

Ambas são superfícies alimentadas por coleção: display (quadro numa TV, tempo real)
e feed (RSS 2.0 que Google Merchant/Meta buscam por agendamento).
"""

from __future__ import annotations

from django.urls import path
from django_eventstream.views import events as eventstream_view

from shopman.shop.views.menuboard import MenuboardDataView, MenuboardPageView
from shopman.shop.views.product_feed import ProductFeedView

urlpatterns = [
    # Feed de produtos (Google Merchant / Meta) — pull; o parceiro agenda o fetch.
    path("feed/<slug:ref>.xml", ProductFeedView.as_view(), name="product-feed"),
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
