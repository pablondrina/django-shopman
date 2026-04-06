from __future__ import annotations

import logging

from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie

logger = logging.getLogger(__name__)

from shopman.offering.models import Collection, Product
from shopman.offering.service import CatalogService
from shopman.utils.monetary import format_money

from ._helpers import (
    _allergen_info,
    _annotate_products,
    _availability_badge,
    _best_auto_promotion_discount_q,
    _collection_icon,
    _cross_sell_products,
    _d1_discount_percent,
    _get_availability,
    _get_channel_listing_ref,
    _get_price_q,
    _hero_data,
    _popular_skus,
    _storefront_session_pricing_hints,
)


def _published_products(listing_ref: str | None) -> QuerySet:
    """Base queryset: published globally AND available in channel listing."""
    qs = Product.objects.filter(is_published=True)
    if listing_ref:
        qs = qs.filter(
            listing_items__listing__ref=listing_ref,
            listing_items__listing__is_active=True,
            listing_items__is_published=True,
            listing_items__is_available=True,
        )
    return qs


@method_decorator(ensure_csrf_cookie, name="dispatch")
class MenuView(View):
    """List products grouped by collection."""

    def get(self, request: HttpRequest, collection: str | None = None) -> HttpResponse:
        listing_ref = _get_channel_listing_ref()

        # HTMX partial: availability preview for home page "Direto do forno" section
        if request.GET.get("partial") == "availability_preview":
            return self._availability_preview(request, listing_ref)

        collections = Collection.objects.filter(is_active=True).order_by("sort_order", "name")
        active_collection = None

        # Popular SKUs for badge annotation
        popular = _popular_skus(limit=5)

        if collection:
            active_collection = get_object_or_404(Collection, slug=collection, is_active=True)
            products = (
                _published_products(listing_ref)
                .filter(collection_items__collection=active_collection)
                .order_by("collection_items__sort_order", "name")
                .distinct()
            )
            sections = [{"collection": active_collection, "products": _annotate_products(list(products), listing_ref=listing_ref, popular_skus=popular, request=request)}]
        else:
            sections = []
            for col in collections:
                products = (
                    _published_products(listing_ref)
                    .filter(collection_items__collection=col)
                    .order_by("collection_items__sort_order", "name")
                    .distinct()
                )
                if products.exists():
                    sections.append({"collection": col, "products": _annotate_products(list(products), listing_ref=listing_ref, popular_skus=popular, request=request)})

            # Products not in any collection
            uncategorized = (
                _published_products(listing_ref)
                .exclude(collection_items__isnull=False)
                .order_by("name")
                .distinct()
            )
            if uncategorized.exists():
                sections.append({
                    "collection": None,
                    "products": _annotate_products(list(uncategorized), listing_ref=listing_ref, popular_skus=popular, request=request),
                })

        # Active promotions
        promotions = self._get_active_promotions()

        # Hero section data (only on main menu, not collection-filtered)
        hero = _hero_data(listing_ref=listing_ref, request=request) if not collection else None

        # Ícones Material Symbols por coleção (slug → ligature name)
        collection_icons = {col.slug: _collection_icon(col.slug) for col in collections}

        return render(request, "storefront/menu.html", {
            "sections": sections,
            "collections": collections,
            "active_collection": active_collection,
            "promotions": promotions,
            "hero": hero,
            "collection_icons": collection_icons,
        })

    def _availability_preview(self, request: HttpRequest, listing_ref: str | None) -> HttpResponse:
        """HTMX partial for home: produtos com disponibilidade + preço/promo (mesmo annotate do cardápio)."""
        popular = _popular_skus(limit=6)
        qs = _published_products(listing_ref)
        if popular:
            products = list(qs.filter(sku__in=popular).distinct()[:6])
        else:
            products = list(qs.order_by("name")[:6])
        items = _annotate_products(products, listing_ref=listing_ref, popular_skus=popular, request=request)
        return render(request, "storefront/partials/availability_preview.html", {"items": items})

    @staticmethod
    def _get_active_promotions() -> list[dict]:
        """Fetch active promotions for display in the catalog."""
        try:
            from shopman.models import Promotion

            now = timezone.now()
            promos = Promotion.objects.filter(
                is_active=True,
                valid_from__lte=now,
                valid_until__gte=now,
            ).order_by("-valid_from")[:5]
            result = []
            for p in promos:
                if p.type == "percent":
                    discount_label = f"{p.value}% OFF"
                else:
                    discount_label = f"R$ {format_money(p.value)} OFF"
                result.append({
                    "name": p.name,
                    "discount_label": discount_label,
                    "type": p.type,
                    "value": p.value,
                })
            return result
        except Exception as e:
            logger.warning("active_promotions_failed: %s", e, exc_info=True)
            return []


class MenuSearchView(View):
    """HTMX partial: search products by name.

    Uses TrigramSimilarity on PostgreSQL for fuzzy matching (tolerates typos).
    Falls back to icontains on SQLite for local dev.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        q = request.GET.get("q", "").strip()
        if len(q) < 2:
            if q:
                return render(request, "storefront/partials/search_results.html", {
                    "items": [],
                    "query": q,
                    "hint": True,
                })
            return HttpResponse("")

        listing_ref = _get_channel_listing_ref()
        products = self._search(q, listing_ref)

        items = _annotate_products(list(products), listing_ref=listing_ref, request=request)

        # If fuzzy returns nothing, show popular products as fallback
        popular_fallback = []
        if not items:
            popular_skus = _popular_skus(limit=4)
            if popular_skus:
                fallback_qs = _published_products(listing_ref).filter(sku__in=popular_skus).distinct()[:4]
                popular_fallback = _annotate_products(list(fallback_qs), listing_ref=listing_ref, request=request)

        return render(request, "storefront/partials/search_results.html", {
            "items": items,
            "query": q,
            "popular_fallback": popular_fallback,
        })

    @staticmethod
    def _search(q: str, listing_ref: str | None) -> QuerySet:
        """Search with TrigramSimilarity (PostgreSQL) or icontains fallback (SQLite)."""
        from django.db import connection

        base = _published_products(listing_ref)

        if connection.vendor == "postgresql":
            try:
                from django.contrib.postgres.search import TrigramSimilarity

                return (
                    base.annotate(
                        similarity=TrigramSimilarity("name", q),
                    )
                    .filter(similarity__gt=0.1)
                    .order_by("-similarity")
                    .distinct()[:20]
                )
            except ImportError:
                pass

        # SQLite fallback: simple icontains
        return base.filter(name__icontains=q).order_by("name").distinct()[:20]


def _load_alternatives(sku: str, listing_ref: str | None, request: HttpRequest | None = None) -> list[dict]:
    """Load alternative products annotated with price and badge."""
    try:
        from shopman.offering.contrib.suggestions import find_alternatives

        candidates = find_alternatives(sku, limit=4, same_collection=False)
        if not candidates:
            return []
        return _annotate_products(candidates, listing_ref=listing_ref, request=request)
    except ImportError:
        return []
    except Exception as e:
        logger.warning("load_alternatives_failed sku=%s: %s", sku, e, exc_info=True)
        return []


def _extract_available_qty(avail: dict | None) -> int | None:
    """Extract total available quantity from availability breakdown."""
    if avail is None:
        return None
    breakdown = avail.get("breakdown", {})
    from decimal import Decimal

    ready = breakdown.get("ready", Decimal("0"))
    in_prod = breakdown.get("in_production", Decimal("0"))
    d1 = breakdown.get("d1", Decimal("0"))
    total = ready + in_prod + d1
    return int(total)


class CartAlternativesView(View):
    """HTMX partial: alternatives for an out-of-stock cart item."""

    def get(self, request: HttpRequest, sku: str) -> HttpResponse:
        listing_ref = _get_channel_listing_ref()
        alternatives = _load_alternatives(sku, listing_ref, request=request)
        return render(request, "storefront/partials/cart_alternatives.html", {
            "sku": sku,
            "alternatives": alternatives,
        })


class ProductDetailView(View):
    """Product detail page."""

    def get(self, request: HttpRequest, sku: str) -> HttpResponse:
        product = get_object_or_404(Product, sku=sku, is_published=True)
        listing_ref = _get_channel_listing_ref()
        base_price_q = _get_price_q(product, listing_ref=listing_ref)
        avail = _get_availability(product.sku)
        badge = _availability_badge(avail, product)

        d1_price_display = None
        original_price_display = None
        is_d1 = False
        price_q = base_price_q
        d1_pct = _d1_discount_percent()

        if avail and badge["css_class"] == "badge-d1" and base_price_q:
            is_d1 = True
            from shopman.utils.monetary import monetary_div

            discount_q = monetary_div(base_price_q * d1_pct, 100)
            d1_price_q = base_price_q - discount_q
            d1_price_display = f"R$ {format_money(d1_price_q)}"
            original_price_display = f"R$ {format_money(base_price_q)}"
            price_q = d1_price_q

        promo_badge = None
        has_promo_price = False
        promo_price_display = None
        promo_original_price_display = None
        ft_hint, sub_hint = _storefront_session_pricing_hints(request)
        if not is_d1 and base_price_q:
            try:
                from shopman.offering.models import CollectionItem

                cols = list(
                    CollectionItem.objects.filter(product=product).values_list(
                        "collection__slug", flat=True,
                    ),
                )
            except Exception as e:
                logger.warning("product_collections_failed sku=%s: %s", product.sku, e, exc_info=True)
                cols = []
            disc_q, promo = _best_auto_promotion_discount_q(
                product.sku,
                base_price_q,
                cols,
                session_total_q=sub_hint,
                fulfillment_type=ft_hint,
            )
            if disc_q > 0 and promo is not None:
                has_promo_price = True
                price_q = base_price_q - disc_q
                promo_price_display = f"R$ {format_money(price_q)}"
                promo_original_price_display = f"R$ {format_money(base_price_q)}"
                if promo.type == "percent":
                    plabel = f"-{promo.value}%"
                else:
                    plabel = f"-R$ {format_money(promo.value)}"
                promo_badge = {"name": promo.name, "label": plabel}

        # Bundle: expand components for display
        components = []
        if product.is_bundle:
            try:
                components = CatalogService.expand(product.sku)
            except Exception as e:
                logger.warning("bundle_expand_failed sku=%s: %s", product.sku, e, exc_info=True)

        # Alternatives when sold out or paused
        alternatives = []
        if badge["css_class"] in ("badge-sold-out", "badge-paused"):
            alternatives = _load_alternatives(product.sku, listing_ref, request=request)

        # Cross-sell ("Compre junto")
        cross_sell = []
        if badge["can_add_to_cart"]:
            cross_sell = _cross_sell_products(product.sku, listing_ref=listing_ref, request=request)

        # Allergen / dietary info
        allergen = _allergen_info(product)

        # Breadcrumb: find first collection for this product
        breadcrumb_collection = None
        try:
            from shopman.offering.models import CollectionItem

            ci = CollectionItem.objects.filter(product=product).select_related("collection").first()
            if ci and ci.collection.is_active:
                breadcrumb_collection = ci.collection
        except Exception as e:
            logger.warning("breadcrumb_collection_failed sku=%s: %s", product.sku, e, exc_info=True)

        # Available quantity for JS notice
        available_qty = _extract_available_qty(avail)

        return render(request, "storefront/product_detail.html", {
            "product": product,
            "price_q": price_q,
            "price_display": f"R$ {format_money(price_q)}" if price_q else None,
            "d1_price_display": d1_price_display,
            "original_price_display": original_price_display,
            "is_d1": is_d1,
            "d1_pct": d1_pct,
            "badge": badge,
            "availability": avail,
            "promo_badge": promo_badge,
            "has_promo_price": has_promo_price,
            "promo_price_display": promo_price_display,
            "promo_original_price_display": promo_original_price_display,
            "components": components,
            "alternatives": alternatives,
            "cross_sell": cross_sell,
            "allergen": allergen,
            "breadcrumb_collection": breadcrumb_collection,
            "available_qty": available_qty,
        })
