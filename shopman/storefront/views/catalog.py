from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie

from shopman.shop.services.storefront_context import (
    fresh_from_oven_skus,
    popular_skus,
)
from shopman.storefront.services import catalog as catalog_service
from shopman.storefront.services.product_cards import (
    annotate_products,
    get_channel_listing_ref,
)

logger = logging.getLogger(__name__)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class MenuView(View):
    """List products grouped by collection."""

    def get(self, request: HttpRequest, collection: str | None = None) -> HttpResponse:
        listing_ref = get_channel_listing_ref()

        if request.GET.get("partial") == "availability_preview":
            return self._availability_preview(request, listing_ref)

        from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
        from shopman.storefront.projections import build_catalog

        if collection is not None:
            catalog_service.ensure_active_collection(collection)
        catalog = build_catalog(
            channel_ref=STOREFRONT_CHANNEL_REF,
            collection_ref=collection,
            request=request,
        )
        return render(request, "storefront/menu.html", {
            "catalog": catalog,
            "catalog_search_index_json": catalog_service.search_index(catalog),
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
            qs = catalog_service.published_products(listing_ref)
            products_by_sku = {p.sku: p for p in qs.filter(sku__in=fresh_skus)}
            products = [products_by_sku[s] for s in fresh_skus if s in products_by_sku]
        else:
            products = []

        if not products:
            popular = popular_skus(limit=6)
            qs = catalog_service.published_products(listing_ref)
            if popular:
                products = list(qs.filter(sku__in=popular).distinct()[:6])
            else:
                products = list(qs.order_by("name")[:6])

        items = annotate_products(
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

        from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
        from shopman.storefront.projections import build_product_detail

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
