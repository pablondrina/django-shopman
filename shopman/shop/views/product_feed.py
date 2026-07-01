"""
Product feed — superfície FEED (Google Merchant / Meta) alimentada por coleção.

Seam de feed PULL: uma superfície com ``capability == "feed"`` e ``content.source
== "collection"`` expõe um feed RSS 2.0 (namespace ``g:`` do Google) público que o
Google Merchant Center e o Meta Commerce Manager buscam por agendamento (ambos
aceitam o XML Google-compatível). Sem credenciais — o parceiro só cola a URL e
verifica o domínio no painel. O push near-real-time (Content API / Catalog Batch
API) é credential-gated e fica para depois (ver docs/plans).

Spec verificada (support.google.com/merchants/answer/7052112 + 6324448 + 6324371):
- Namespace: ``http://base.google.com/ns/1.0`` (prefixo ``g:``).
- Obrigatórios: id, title, description, link, image_link, availability, price.
- availability: ``in_stock`` | ``out_of_stock``. price: ``12.00 BRL`` (ponto decimal).
- Padaria artesanal sem GTIN/marca de fabricante → ``identifier_exists = no``
  (escape sancionado); mantemos ``brand`` = nome da loja quando houver.
- ``custom_label_0`` = coleção primária → análogo das smart collections p/ anúncios.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views import View

logger = logging.getLogger(__name__)


class ProductFeedError(Exception):
    pass


def _resolve_feed_surface(surface_ref: str):
    from shopman.shop.config import ChannelConfig
    from shopman.shop.models import Channel

    channel = Channel.objects.filter(ref=surface_ref, is_active=True).first()
    if channel is None:
        raise ProductFeedError("surface not found")
    cfg = ChannelConfig.for_channel(channel)
    if cfg.capability != "feed":
        raise ProductFeedError("surface is not a feed")
    if cfg.content.source != "collection" or not cfg.content.collection:
        raise ProductFeedError("feed has no source collection")
    return channel, cfg.content.collection


def _storefront_base(request) -> str:
    base = getattr(settings, "SHOPMAN_STOREFRONT_URL", "") or ""
    if base:
        return base.rstrip("/")
    return request.build_absolute_uri("/").rstrip("/")


def build_feed_items(surface_ref: str, request) -> list[dict]:
    """Itens do feed (dicts prontos p/ o template). Formatação = camada de view."""
    from shopman.offerman.models import Collection, ListingItem

    _channel, collection_ref = _resolve_feed_surface(surface_ref)
    coll = Collection.objects.filter(ref=collection_ref).first()
    if coll is None:
        raise ProductFeedError("source collection not found")

    base = _storefront_base(request)
    overrides = {
        i.product.sku: i
        for i in ListingItem.objects.filter(listing__ref=surface_ref).select_related("product")
    }

    items: list[dict] = []
    for product in coll.product_queryset().prefetch_related("collection_items__collection"):
        # image_link é obrigatório no Google/Meta — itens sem imagem seriam
        # reprovados; omitimos do feed (feed continua válido).
        if not product.image_url:
            continue
        override = overrides.get(product.sku)
        price_q = override.price_q if override is not None else product.base_price_q
        available = product.is_published and product.is_sellable
        if override is not None:
            available = available and override.is_published and override.is_sellable

        primary = next((ci for ci in product.collection_items.all() if ci.is_primary), None)
        items.append({
            "id": product.sku,
            "title": product.name[:150],
            "description": (product.long_description or product.short_description or product.name)[:5000],
            "link": f"{base}/produto/{product.sku}",
            "image_link": product.image_url,
            "availability": "in_stock" if available else "out_of_stock",
            "price": f"{price_q / 100:.2f} BRL",
            "product_type": primary.collection.name if primary else coll.name,
            "custom_label_0": primary.collection.ref if primary else coll.ref,
        })
    return items


class ProductFeedView(View):
    """Feed RSS 2.0 público (Google/Meta) de uma superfície feed."""

    def get(self, request, ref: str):
        try:
            items = build_feed_items(ref, request)
        except ProductFeedError as exc:
            raise Http404(str(exc)) from exc

        brand = ""
        try:
            from shopman.shop.models import Shop

            shop = Shop.objects.only("name").first()
            brand = shop.name if shop else ""
        except Exception:
            logger.debug("product_feed.brand_lookup_failed", exc_info=True)

        content = render(
            request,
            "feed/products.xml",
            {"ref": ref, "brand": brand, "items": items, "link": _storefront_base(request)},
        ).content
        return HttpResponse(content, content_type="application/xml; charset=utf-8")
