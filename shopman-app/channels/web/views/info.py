from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views import View
from shopman.offering.models import Collection, Product
from shopman.ordering.models import Order
from shopman.utils.monetary import format_money
from shopman.utils.phone import normalize_phone

from .auth import get_authenticated_customer
from .tracking import STATUS_COLORS, STATUS_LABELS


class HowItWorksView(View):
    """Static page explaining the ordering process."""

    def get(self, request: HttpRequest) -> HttpResponse:
        return render(request, "storefront/como_funciona.html")


class OrderHistoryView(View):
    """Order history — requires session auth (OTP verified)."""

    def get(self, request: HttpRequest) -> HttpResponse:
        customer = get_authenticated_customer(request)
        if customer:
            phone = customer.phone
            orders = self._get_orders(phone)
            return render(request, "storefront/history.html", {
                "orders": orders,
                "phone_value": phone,
                "is_verified": True,
            })
        return render(request, "storefront/history.html", {"orders": None})

    def post(self, request: HttpRequest) -> HttpResponse:
        phone_raw = request.POST.get("phone", "").strip()
        errors = {}

        if not phone_raw:
            errors["phone"] = "Telefone é obrigatório."
            return render(request, "storefront/history.html", {
                "orders": None,
                "errors": errors,
                "phone_value": phone_raw,
            })

        try:
            phone = normalize_phone(phone_raw)
        except Exception:
            errors["phone"] = "Telefone inválido. Use formato com DDD, ex: (43) 99999-9999"
            return render(request, "storefront/history.html", {
                "orders": None,
                "errors": errors,
                "phone_value": phone_raw,
            })

        if not phone:
            errors["phone"] = "Telefone inválido."
            return render(request, "storefront/history.html", {
                "orders": None,
                "errors": errors,
                "phone_value": phone_raw,
            })

        # If already verified for this phone, show orders directly
        customer = get_authenticated_customer(request)
        if customer and customer.phone == phone:
            orders = self._get_orders(phone)
            return render(request, "storefront/history.html", {
                "orders": orders,
                "phone_value": phone_raw,
                "is_verified": True,
            })

        # Check if customer exists
        from shopman.customers.services import customer as customer_service

        found = customer_service.get_by_phone(phone)
        if not found:
            return render(request, "storefront/history.html", {
                "orders": None,
                "not_found": True,
                "phone_value": phone_raw,
            })

        # Customer exists but not verified — require OTP
        return render(request, "storefront/history.html", {
            "orders": None,
            "needs_verification": True,
            "customer_name": found.first_name or found.name,
            "phone_value": phone,
        })

    @staticmethod
    def _get_orders(phone: str) -> list[dict]:
        orders = Order.objects.filter(
            handle_type="phone",
            handle_ref=phone,
        ).order_by("-created_at")[:50]

        enriched = []
        for order in orders:
            enriched.append({
                "ref": order.ref,
                "created_at": order.created_at,
                "total_display": f"R$ {format_money(order.total_q)}",
                "status": order.status,
                "status_label": STATUS_LABELS.get(order.status, order.status),
                "status_color": STATUS_COLORS.get(order.status, "bg-gray-100 text-gray-800"),
            })
        return enriched


class SitemapView(View):
    """Generate a simple XML sitemap with menu, collections, and product URLs."""

    def get(self, request: HttpRequest) -> HttpResponse:
        from django.urls import reverse

        urls = []
        base = request.build_absolute_uri("/").rstrip("/")

        # Menu
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
