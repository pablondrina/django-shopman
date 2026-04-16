from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views import View
from shopman.offerman.models import Collection, Product
from shopman.orderman.models import Order
from shopman.shop.projections.order_history import build_order_history

from ._helpers import _is_v2_request
from .auth import get_authenticated_customer


class HowItWorksView(View):
    """Static page explaining the ordering process."""

    def get(self, request: HttpRequest) -> HttpResponse:
        if _is_v2_request(request):
            return render(request, "storefront/v2/como_funciona.html")
        return render(request, "storefront/como_funciona.html")


class OrderHistoryView(View):
    """Order history — requires session auth (OTP verified)."""

    _ACTIVE_STATUSES = frozenset({"new", "confirmed", "preparing", "ready", "dispatched"})

    def get(self, request: HttpRequest) -> HttpResponse:
        # Badge-only: return active order count for bottom nav polling
        if request.GET.get("badge_only"):
            customer = get_authenticated_customer(request)
            if not customer:
                return HttpResponse("")
            count = Order.objects.filter(
                handle_type="phone",
                handle_ref=customer.phone,
                status__in=self._ACTIVE_STATUSES,
            ).count()
            if count:
                return HttpResponse(
                    f'<span class="absolute -top-1 -right-1 bg-primary text-white text-[10px] font-bold '
                    f'rounded-full w-4 h-4 flex items-center justify-center">{count}</span>'
                )
            return HttpResponse("")

        customer = get_authenticated_customer(request)
        if not customer:
            return redirect("/login/?next=/meus-pedidos/")

        filter_param = request.GET.get("filter", "todos")
        history = build_order_history(customer, filter_param=filter_param)

        if _is_v2_request(request):
            return render(request, "storefront/v2/order_history.html", {"history": history})
        return render(request, "storefront/history.html", {
            "orders": [
                {
                    "ref": o.ref,
                    "created_at": o.created_at_display,
                    "total_display": o.total_display,
                    "status": o.status,
                    "status_label": o.status_label,
                    "status_color": o.status_color,
                }
                for o in history.orders
            ],
            "phone_value": history.phone_display,
            "active_filter": history.active_filter,
            "filter_options": list(history.filter_options),
        })


class SitemapView(View):
    """Generate a simple XML sitemap with menu, collections, and product URLs."""

    def get(self, request: HttpRequest) -> HttpResponse:
        from django.urls import reverse

        urls = []
        base = request.build_absolute_uri("/").rstrip("/")

        # Home + Menu
        urls.append({"loc": base + reverse("storefront:home"), "priority": "1.0", "changefreq": "weekly"})
        urls.append({"loc": base + reverse("storefront:menu"), "priority": "1.0", "changefreq": "daily"})
        urls.append({"loc": base + reverse("storefront:como_funciona"), "priority": "0.5", "changefreq": "monthly"})

        # Collections
        for col in Collection.objects.filter(is_active=True):
            urls.append({
                "loc": base + reverse("storefront:menu_collection", args=[col.ref]),
                "priority": "0.8",
                "changefreq": "daily",
            })

        # Products
        for product in Product.objects.filter(is_published=True):
            urls.append({
                "loc": base + reverse("storefront:product_detail", args=[product.sku]),
                "priority": "0.7",
                "changefreq": "daily",
            })

        return render(request, "storefront/sitemap.xml", {"urls": urls}, content_type="application/xml")
