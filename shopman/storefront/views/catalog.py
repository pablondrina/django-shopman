from __future__ import annotations

import logging

from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from shopman.offerman.models import Collection, Product

from shopman.storefront.services.storefront_context import (
    fresh_from_oven_skus,
    popular_skus,
)

from ._helpers import (
    _annotate_products,
    _get_channel_listing_ref,
)

logger = logging.getLogger(__name__)


def _published_products(listing_ref: str | None) -> QuerySet:
    """Base queryset: visible in the current listing."""
    qs = Product.objects.filter(is_published=True)
    if listing_ref:
        qs = qs.filter(
            listing_items__listing__ref=listing_ref,
            listing_items__listing__is_active=True,
            listing_items__is_published=True,
        )
    return qs


def _build_search_index(catalog) -> list[dict]:
    """Índice leve pra busca client-side no overlay do menu.

    Um registro por item de seção, dedupado por sku (o mesmo item pode aparecer
    em uma dinâmica + sua coleção estática). Inclui keywords pra melhor ranking.
    """
    seen: set[str] = set()
    records: list[dict] = []
    keywords_by_sku: dict[str, list[str]] = {}

    try:
        skus_all = [item.sku for sec in catalog.sections for item in sec.items]
        if skus_all:
            prods = Product.objects.filter(sku__in=skus_all).prefetch_related("keywords")
            for p in prods:
                try:
                    keywords_by_sku[p.sku] = [str(t.name) for t in p.keywords.all()]
                except Exception:
                    keywords_by_sku[p.sku] = []
    except Exception:
        keywords_by_sku = {}

    for section in catalog.sections:
        for item in section.items:
            if item.sku in seen:
                continue
            seen.add(item.sku)
            records.append({
                "sku": item.sku,
                "name": item.name,
                "price": item.price_display,
                "image": item.image_url or "",
                "section": section.label,
                "keywords": keywords_by_sku.get(item.sku, []),
            })
    return records


@method_decorator(ensure_csrf_cookie, name="dispatch")
class MenuView(View):
    """List products grouped by collection."""

    def get(self, request: HttpRequest, collection: str | None = None) -> HttpResponse:
        listing_ref = _get_channel_listing_ref()

        if request.GET.get("partial") == "availability_preview":
            return self._availability_preview(request, listing_ref)

        from shopman.storefront.projections import build_catalog
        from shopman.storefront.constants import STOREFRONT_CHANNEL_REF

        if collection is not None:
            get_object_or_404(Collection, ref=collection, is_active=True)
        catalog = build_catalog(
            channel_ref=STOREFRONT_CHANNEL_REF,
            collection_ref=collection,
            request=request,
        )
        reorder_skipped = request.session.pop("reorder_skipped", None)
        return render(request, "storefront/menu.html", {
            "catalog": catalog,
            "reorder_skipped": reorder_skipped,
            "catalog_search_index_json": _build_search_index(catalog),
        })

    def _availability_preview(self, request: HttpRequest, listing_ref: str | None) -> HttpResponse:
        """HTMX partial for home: produtos com disponibilidade + preço/promo.

        Prioritises "fresh from the oven" (recent production moves) and falls
        back to popular SKUs when nothing was produced in the last hour.
        """
        fresh = fresh_from_oven_skus(limit=6)
        freshness_map: dict[str, str] = {}

        if fresh:
            fresh_skus = [f["sku"] for f in fresh]
            freshness_map = {f["sku"]: f["freshness_label"] for f in fresh}
            qs = _published_products(listing_ref)
            products_by_sku = {p.sku: p for p in qs.filter(sku__in=fresh_skus)}
            products = [products_by_sku[s] for s in fresh_skus if s in products_by_sku]
        else:
            products = []

        if not products:
            popular = popular_skus(limit=6)
            qs = _published_products(listing_ref)
            if popular:
                products = list(qs.filter(sku__in=popular).distinct()[:6])
            else:
                products = list(qs.order_by("name")[:6])

        items = _annotate_products(
            products, listing_ref=listing_ref,
            popular_skus=popular_skus(limit=6) if not fresh else set(),
            request=request,
        )

        for item in items:
            item["freshness_label"] = freshness_map.get(item["product"].sku, "")

        return render(
            request,
            "storefront/partials/availability_preview.html",
            {"items": items, "has_fresh": bool(freshness_map)},
        )


class ProductDetailView(View):
    """Product detail page."""

    def get(self, request: HttpRequest, sku: str) -> HttpResponse:
        from django.http import Http404

        from shopman.storefront.projections import build_product_detail
        from shopman.storefront.constants import STOREFRONT_CHANNEL_REF

        projection = build_product_detail(
            sku=sku,
            channel_ref=STOREFRONT_CHANNEL_REF,
            request=request,
        )
        if projection is None:
            raise Http404("Product not found")
        return render(request, "storefront/product_detail.html", {"product": projection})


class TipsView(View):
    """Static page: storage and conservation tips."""

    def get(self, request: HttpRequest) -> HttpResponse:
        return render(request, "storefront/dicas.html")
