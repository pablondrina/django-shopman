from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views import View

from shopman.offerman.models import Collection, Product
from shopman.orderman.models import Order
from shopman.utils.monetary import format_money

from .auth import get_authenticated_customer
from .tracking import STATUS_COLORS, STATUS_LABELS


class HowItWorksView(View):
    """Static page explaining the ordering process."""

    def get(self, request: HttpRequest) -> HttpResponse:
        return render(request, "storefront/como_funciona.html")


class OrderHistoryView(View):
    """Order history — requires session auth (OTP verified)."""

    _ACTIVE_STATUSES = {"new", "confirmed", "preparing", "ready", "dispatched"}

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
        orders = self._get_orders(customer.phone, filter_param)
        return render(request, "storefront/history.html", {
            "orders": orders,
            "phone_value": customer.phone,
            "active_filter": filter_param,
            "filter_options": [
                ("todos", "Todos"),
                ("ativos", "Ativos"),
                ("anteriores", "Anteriores"),
            ],
        })

    @classmethod
    def _get_orders(cls, phone: str, filter_param: str = "todos") -> list[dict]:
        qs = Order.objects.filter(
            handle_type="phone",
            handle_ref=phone,
        ).order_by("-created_at")

        if filter_param == "ativos":
            qs = qs.filter(status__in=cls._ACTIVE_STATUSES)
        elif filter_param == "anteriores":
            qs = qs.exclude(status__in=cls._ACTIVE_STATUSES)

        enriched = []
        for order in qs[:50]:
            enriched.append({
                "ref": order.ref,
                "created_at": order.created_at,
                "total_display": f"R$ {format_money(order.total_q)}",
                "status": order.status,
                "status_label": STATUS_LABELS.get(order.status, order.status),
                "status_color": STATUS_COLORS.get(order.status, "bg-muted text-muted-foreground"),
            })
        return enriched


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
                "loc": base + reverse("storefront:menu_collection", args=[col.slug]),
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
