from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views import View

from shopman.storefront.projections.order_history import build_order_history
from shopman.storefront.services import catalog as catalog_service
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
        urls = catalog_service.sitemap_urls(request)
        return render(request, "storefront/sitemap.xml", {"urls": urls}, content_type="application/xml")
