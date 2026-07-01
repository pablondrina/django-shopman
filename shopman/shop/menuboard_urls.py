"""URLs públicas dos Expositores (shop.Showcase) — menuboard (TV) e feed (Google/Meta).

Um Expositor exibe um conjunto de coleções para fora, sem transacionar: menuboard
(quadro numa TV, tempo real via SSE) e feed (RSS 2.0 que Google/Meta buscam agendado).
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
    # Stream público ``stock-catalog``: o motor de disponibilidade emite nele em toda
    # mudança de estado do produto (ver shop/handlers/_sse_emitters.py). Todos os
    # menuboards assinam o mesmo canal (refletem o estado canônico do catálogo).
    path(
        "menuboard/<slug:ref>/events/",
        eventstream_view,
        {"channels": ["stock-catalog"]},
        name="menuboard-events",
    ),
]
