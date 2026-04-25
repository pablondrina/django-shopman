from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views import View
from shopman.offerman.models import Collection, Product

from shopman.storefront.projections.order_history import build_order_history
from shopman.storefront.services import orders as order_service

from .auth import get_authenticated_customer


class HowItWorksView(View):
    """Static page explaining the ordering process."""

    def get(self, request: HttpRequest) -> HttpResponse:
        return render(request, "storefront/como_funciona.html")


class OrderHistoryView(View):
    """Order history — requires session auth (OTP verified)."""

    def get(self, request: HttpRequest) -> HttpResponse:
        # Badge-only: return active order count for bottom nav polling
        if request.GET.get("badge_only"):
            customer = get_authenticated_customer(request)
            if not customer:
                return HttpResponse("")
            count = order_service.active_order_count_for_phone(customer.phone)
            if count:
                return HttpResponse(
                    f'<span data-order-count="{count}" '
                    f'class="absolute -top-1 -right-1 bg-primary text-white text-[10px] font-bold '
                    f'rounded-full w-4 h-4 flex items-center justify-center motion-safe:animate-pulse">'
                    f'{count}</span>'
                )
            return HttpResponse("")

        customer = get_authenticated_customer(request)
        if not customer:
            return redirect("/login/?next=/meus-pedidos/")

        filter_param = request.GET.get("filter", "todos")
        history = build_order_history(customer, filter_param=filter_param)
        return render(request, "storefront/order_history.html", {"history": history})


class SitemapView(View):
    """Generate an XML sitemap with menu, collections, product URLs + images + lastmod."""

    def get(self, request: HttpRequest) -> HttpResponse:
        from django.urls import reverse

        from shopman.shop.models import Shop

        urls = []
        base = request.build_absolute_uri("/").rstrip("/")

        shop = Shop.load()
        shop_updated = shop.updated_at.isoformat() if shop and getattr(shop, "updated_at", None) else None

        # Home + Menu
        urls.append({
            "loc": base + reverse("storefront:home"),
            "priority": "1.0", "changefreq": "weekly",
            "lastmod": shop_updated,
        })
        urls.append({
            "loc": base + reverse("storefront:menu"),
            "priority": "1.0", "changefreq": "daily",
            "lastmod": shop_updated,
        })
        urls.append({
            "loc": base + reverse("storefront:como_funciona"),
            "priority": "0.5", "changefreq": "monthly",
            "lastmod": shop_updated,
        })

        # Collections
        for col in Collection.objects.filter(is_active=True):
            urls.append({
                "loc": base + reverse("storefront:menu_collection", args=[col.ref]),
                "priority": "0.8",
                "changefreq": "daily",
                "lastmod": col.updated_at.isoformat() if getattr(col, "updated_at", None) else None,
            })

        # Products — com <image:image> e lastmod real
        for product in Product.objects.filter(is_published=True):
            image_url = None
            if getattr(product, "image", None) and getattr(product.image, "name", ""):
                image_url = request.build_absolute_uri(product.image.url)
            elif getattr(product, "image_url", ""):
                url = product.image_url
                image_url = url if url.startswith("http") else base + url

            urls.append({
                "loc": base + reverse("storefront:product_detail", args=[product.sku]),
                "priority": "0.7",
                "changefreq": "daily",
                "lastmod": product.updated_at.isoformat() if getattr(product, "updated_at", None) else None,
                "image_url": image_url,
                "image_title": product.name,
            })

        return render(request, "storefront/sitemap.xml", {"urls": urls}, content_type="application/xml")
