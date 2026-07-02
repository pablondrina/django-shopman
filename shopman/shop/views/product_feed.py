"""
Product feed — o 🛰 Expositor de tipo ``google``/``meta`` (feed RSS 2.0 público).

Um Expositor (``shop.Showcase``) de feed compõe N coleções; cada coleção vira o
``custom_label_0`` do produto (o análogo das smart collections p/ anúncios — Google
custom_labels, Meta product sets). Pull: Google Merchant e Meta buscam a URL agendado
(ambos aceitam o XML ``g:``). O único campo que diverge é ``availability`` — Google usa
underscore, Meta usa espaço; o ``kind`` do Expositor decide.

Spec verificada (2026-07-01): support.google.com/merchants/answer/7052112 (Google) +
facebook.com/business/help/120325381656392 (Meta). Detalhes em
docs/plans/CATALOG-FEEDS-GOOGLE-META.md.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views import View

logger = logging.getLogger(__name__)

# availability diverge por plataforma (verificado): Google underscore, Meta espaço.
_AVAILABILITY = {
    "google": {True: "in_stock", False: "out_of_stock"},
    "meta": {True: "in stock", False: "out of stock"},
}


class ProductFeedError(Exception):
    pass


def _resolve_feed_showcase(ref: str):
    from shopman.shop.models import Showcase

    sc = Showcase.objects.filter(ref=ref, is_active=True).first()
    if sc is None or not sc.is_feed:
        raise ProductFeedError("not a feed showcase")
    return sc


def _storefront_base(request) -> str:
    base = getattr(settings, "SHOPMAN_STOREFRONT_URL", "") or ""
    return (base or request.build_absolute_uri("/")).rstrip("/")


def build_feed_items(ref: str, request) -> list[dict]:
    """Itens do feed a partir das coleções do Expositor. Formatação = camada de view."""
    from shopman.offerman.models import Collection

    showcase = _resolve_feed_showcase(ref)
    platform = "meta" if showcase.kind == "meta" else "google"
    avail = _AVAILABILITY[platform]
    base = _storefront_base(request)

    colls = {c.ref: c for c in Collection.objects.filter(ref__in=showcase.collection_refs())}
    paused = showcase.paused_skus()  # pausa LOCAL do expositor (a global é do produto)

    items: list[dict] = []
    seen: set[str] = set()
    for coll_ref in showcase.collection_refs():
        coll = colls.get(coll_ref)
        if coll is None:
            continue
        for product in coll.product_queryset():
            if product.sku in seen or not product.image_url:
                # dedupe (1ª coleção do expositor vence o custom_label); item sem
                # imagem é omitido (image_link é obrigatório — seria reprovado).
                continue
            seen.add(product.sku)
            available = product.is_published and product.is_sellable and product.sku not in paused
            items.append({
                "id": product.sku,
                "title": product.name[:150],
                "description": (product.long_description or product.short_description or product.name)[:5000],
                "link": f"{base}/produto/{product.sku}",
                "image_link": product.image_url,
                "availability": avail[available],
                "price": f"{product.base_price_q / 100:.2f} BRL",
                "product_type": coll.name,
                "custom_label_0": coll.ref,
            })
    return items


class ProductFeedView(View):
    """Feed RSS 2.0 público (Google/Meta) de um Expositor de feed."""

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
