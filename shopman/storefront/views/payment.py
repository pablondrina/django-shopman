from __future__ import annotations

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from shopman.orderman.models import Order

from shopman.shop.services import payment as payment_svc


class PaymentView(View):
    """Payment page — PIX (QR code) or Card (Stripe Elements)."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = get_object_or_404(Order, ref=ref)

        if payment_svc.get_payment_status(order) == "captured":
            return redirect("storefront:order_tracking", ref=ref)
        if order.status == "cancelled":
            return redirect("storefront:order_tracking", ref=ref)

        from shopman.storefront.projections import build_payment

        proj = build_payment(order)
        return render(request, "storefront/payment.html", {"payment": proj})


class PaymentStatusView(View):
    """HTMX partial: polls payment status, redirects when paid."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = get_object_or_404(Order, ref=ref)

        from shopman.storefront.projections import build_payment_status

        proj = build_payment_status(order)
        if proj.is_paid:
            response = HttpResponse("")
            response["HX-Redirect"] = proj.redirect_url
            return response
        return render(request, "storefront/partials/payment_status.html", {"payment_status": proj})


class MockPaymentConfirmView(View):
    """
    DEV ONLY: Simulate PIX payment confirmation.

    Delegates the Payman transition and order lifecycle effects to shop services.
    """

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        # URL only registered in DEBUG mode (urls.py), but belt-and-suspenders:
        if not settings.DEBUG:
            raise Http404

        order = get_object_or_404(Order, ref=ref)

        payment_svc.mock_confirm(order)

        return redirect("storefront:order_tracking", ref=ref)
