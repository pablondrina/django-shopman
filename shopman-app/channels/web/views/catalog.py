from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from shopman.offering.models import Collection, Product
from shopman.utils.monetary import format_money

from . import _helpers
from ._helpers import _annotate_products, _availability_badge, _get_availability, _get_price_q


@method_decorator(ensure_csrf_cookie, name="dispatch")
class MenuView(View):
    """List products grouped by collection."""

    def get(self, request: HttpRequest, collection: str | None = None) -> HttpResponse:
        collections = Collection.objects.filter(is_active=True).order_by("sort_order", "name")
        active_collection = None

        if collection:
            active_collection = get_object_or_404(Collection, slug=collection, is_active=True)
            products = (
                Product.objects.filter(
                    is_published=True,
                    collection_items__collection=active_collection,
                )
                .order_by("collection_items__sort_order", "name")
                .distinct()
            )
            sections = [{"collection": active_collection, "products": _annotate_products(list(products))}]
        else:
            sections = []
            for col in collections:
                products = (
                    Product.objects.filter(
                        is_published=True,
                        collection_items__collection=col,
                    )
                    .order_by("collection_items__sort_order", "name")
                    .distinct()
                )
                if products.exists():
                    sections.append({"collection": col, "products": _annotate_products(list(products))})

            # Products not in any collection
            uncategorized = (
                Product.objects.filter(is_published=True)
                .exclude(collection_items__isnull=False)
                .order_by("name")
            )
            if uncategorized.exists():
                sections.append({
                    "collection": None,
                    "products": _annotate_products(list(uncategorized)),
                })

        return render(request, "storefront/menu.html", {
            "sections": sections,
            "collections": collections,
            "active_collection": active_collection,
        })


class MenuSearchView(View):
    """HTMX partial: search products by name."""

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

        products = Product.objects.filter(
            is_published=True,
            name__icontains=q,
        ).order_by("name")[:20]

        items = _annotate_products(list(products))
        return render(request, "storefront/partials/search_results.html", {
            "items": items,
            "query": q,
        })


class ProductDetailView(View):
    """Product detail page."""

    def get(self, request: HttpRequest, sku: str) -> HttpResponse:
        product = get_object_or_404(Product, sku=sku, is_published=True)
        price_q = _get_price_q(product)
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

        return render(request, "storefront/product_detail.html", {
            "product": product,
            "price_q": price_q,
            "price_display": f"R$ {format_money(price_q)}" if price_q else None,
            "d1_price_display": d1_price_display,
            "original_price_display": original_price_display,
            "is_d1": is_d1,
            "badge": badge,
            "availability": avail,
        })
