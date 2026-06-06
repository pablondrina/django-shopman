from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie

from shopman.shop.projections.storefront_context import (
    fresh_from_oven_skus,
    popular_skus,
)
from shopman.storefront.presentation import get_channel_listing_ref
from shopman.storefront.presentation.merchandising import freshness_label
from shopman.storefront.services import catalog as catalog_service

logger = logging.getLogger(__name__)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class MenuView(View):
    """List products grouped by collection."""

    def get(self, request: HttpRequest, collection: str | None = None) -> HttpResponse:
        listing_ref = get_channel_listing_ref()

        if request.GET.get("partial") == "home_availability":
            return self._home_availability(request, listing_ref)

        from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
        from shopman.storefront.presentation import build_catalog

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

    def _home_availability(self, request: HttpRequest, listing_ref: str | None) -> HttpResponse:
        """HTMX partial for home: produtos com disponibilidade + preço/promo.

        Prioritises "fresh from the oven" (recent production moves) and falls
        back to popular SKUs when nothing was produced in the last hour. Renders
        the canonical catalog card (CatalogItemProjection) — one card shape.
        """
        from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
        from shopman.storefront.presentation import build_catalog_items_for_skus

        fresh = fresh_from_oven_skus(limit=6)
        freshness_by_sku: dict[str, str] = {}

        if fresh:
            skus = [f["sku"] for f in fresh]
            freshness_by_sku = {f["sku"]: freshness_label(f["minutes_ago"]) for f in fresh}
        else:
            popular = popular_skus(limit=6)
            if popular:
                skus = list(popular)[:6]
            else:
                qs = catalog_service.published_products(listing_ref).order_by("name")
                skus = [p.sku for p in qs[:6]]

        items = build_catalog_items_for_skus(
            skus,
            channel_ref=STOREFRONT_CHANNEL_REF,
            request=request,
            freshness_by_sku=freshness_by_sku,
        )

        return render(
            request,
            "storefront/partials/home_availability.html",
            {"items": items},
        )


class ProductDetailView(View):
    """Product detail page."""

    def get(self, request: HttpRequest, sku: str) -> HttpResponse:
        from django.http import Http404

        from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
        from shopman.storefront.presentation import build_product_detail

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
