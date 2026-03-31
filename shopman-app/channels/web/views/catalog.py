from __future__ import annotations

from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from shopman.offering.models import Collection, Product
from shopman.offering.service import CatalogService
from shopman.utils.monetary import format_money

from . import _helpers
from ._helpers import (
    _allergen_info,
    _annotate_products,
    _availability_badge,
    _collection_emoji,
    _cross_sell_products,
    _get_availability,
    _get_channel_listing_ref,
    _get_price_q,
    _hero_data,
    _popular_skus,
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
            sections = [{"collection": active_collection, "products": _annotate_products(list(products), listing_ref=listing_ref, popular_skus=popular)}]
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
                    sections.append({"collection": col, "products": _annotate_products(list(products), listing_ref=listing_ref, popular_skus=popular)})

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
                    "products": _annotate_products(list(uncategorized), listing_ref=listing_ref, popular_skus=popular),
                })

        # Active promotions
        promotions = self._get_active_promotions()

        # Hero section data (only on main menu, not collection-filtered)
        hero = _hero_data(listing_ref=listing_ref) if not collection else None

        # Collection emojis
        collection_emojis = {col.slug: _collection_emoji(col.slug) for col in collections}

        return render(request, "storefront/menu.html", {
            "sections": sections,
            "collections": collections,
            "active_collection": active_collection,
            "promotions": promotions,
            "hero": hero,
            "collection_emojis": collection_emojis,
        })

    @staticmethod
    def _get_active_promotions() -> list[dict]:
        """Fetch active promotions for display in the catalog."""
        try:
            from shop.models import Promotion

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
        except Exception:
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

        items = _annotate_products(list(products), listing_ref=listing_ref)

        # If fuzzy returns nothing, show popular products as fallback
        popular_fallback = []
        if not items:
            popular_skus = _popular_skus(limit=4)
            if popular_skus:
                fallback_qs = _published_products(listing_ref).filter(sku__in=popular_skus).distinct()[:4]
                popular_fallback = _annotate_products(list(fallback_qs), listing_ref=listing_ref)

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


def _load_alternatives(sku: str, listing_ref: str | None) -> list[dict]:
    """Load alternative products annotated with price and badge."""
    try:
        from shopman.offering.contrib.suggestions import find_alternatives

        candidates = find_alternatives(sku, limit=4, same_collection=False)
        if not candidates:
            return []
        return _annotate_products(candidates, listing_ref=listing_ref)
    except ImportError:
        return []
    except Exception:
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


class ProductDetailView(View):
    """Product detail page."""

    def get(self, request: HttpRequest, sku: str) -> HttpResponse:
        product = get_object_or_404(Product, sku=sku, is_published=True)
        listing_ref = _get_channel_listing_ref()
        price_q = _get_price_q(product, listing_ref=listing_ref)
        avail = _get_availability(product.sku)
        badge = _availability_badge(avail, product)

        d1_price_display = None
        original_price_display = None
        is_d1 = False
        if avail and badge["css_class"] == "badge-d1" and price_q:
            is_d1 = True
            from shopman.utils.monetary import monetary_div

            d1_pct = _helpers._d1_discount_percent()
            discount_q = monetary_div(price_q * d1_pct, 100)
            d1_price_q = price_q - discount_q
            d1_price_display = f"R$ {format_money(d1_price_q)}"
            original_price_display = f"R$ {format_money(price_q)}"
            price_q = d1_price_q

        # Bundle: expand components for display
        components = []
        if product.is_bundle:
            try:
                components = CatalogService.expand(product.sku)
            except Exception:
                pass

        # Alternatives when sold out or paused
        alternatives = []
        if badge["css_class"] in ("badge-sold-out", "badge-paused"):
            alternatives = _load_alternatives(product.sku, listing_ref)

        # Cross-sell ("Compre junto")
        cross_sell = []
        if badge["can_add_to_cart"]:
            cross_sell = _cross_sell_products(product.sku, listing_ref=listing_ref)

        # Allergen / dietary info
        allergen = _allergen_info(product)

        # Breadcrumb: find first collection for this product
        breadcrumb_collection = None
        try:
            from shopman.offering.models import CollectionItem

            ci = CollectionItem.objects.filter(product=product).select_related("collection").first()
            if ci and ci.collection.is_active:
                breadcrumb_collection = ci.collection
        except Exception:
            pass

        # Available quantity for JS notice
        available_qty = _extract_available_qty(avail)

        return render(request, "storefront/product_detail.html", {
            "product": product,
            "price_q": price_q,
            "price_display": f"R$ {format_money(price_q)}" if price_q else None,
            "d1_price_display": d1_price_display,
            "original_price_display": original_price_display,
            "is_d1": is_d1,
            "badge": badge,
            "availability": avail,
            "components": components,
            "alternatives": alternatives,
            "cross_sell": cross_sell,
            "allergen": allergen,
            "breadcrumb_collection": breadcrumb_collection,
            "available_qty": available_qty,
        })
