from __future__ import annotations

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views import View

from ..services import orders as order_service


class PaymentView(View):
    """Payment page — PIX (QR code) or Card (Stripe Elements)."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = order_service.get_order(ref)
        order_service.resolve_payment_timeout_if_due(order)

        if order_service.is_cancelled(order):
            return redirect("storefront:order_tracking", ref=ref)
        if order_service.payment_is_sufficient(order):
            return redirect("storefront:order_tracking", ref=ref)

        intent_ready = order_service.ensure_payment_intent(order)
        if order_service.payment_is_sufficient(order):
            return redirect("storefront:order_tracking", ref=ref)

        from shopman.storefront.projections import build_payment

        proj = build_payment(order)
        if not intent_ready and _is_digital_payment(order) and order.status == "confirmed":
            return render(request, "storefront/payment.html", {"payment": proj})
        if not intent_ready:
            return redirect("storefront:order_tracking", ref=ref)
        return render(request, "storefront/payment.html", {"payment": proj})


class PaymentStatusView(View):
    """HTMX partial: polls payment status, redirects when paid."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = order_service.get_order(ref)
        order_service.resolve_payment_timeout_if_due(order)

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

        order = order_service.get_order(ref)
        order_service.resolve_payment_timeout_if_due(order)

        if order_service.payment_is_sufficient(order):
            return redirect("storefront:order_tracking", ref=ref)

        if not order_service.ensure_payment_intent(order):
            if _is_digital_payment(order) and order.status == "confirmed":
                return redirect("storefront:order_payment", ref=ref)
            return redirect("storefront:order_tracking", ref=ref)
        if not order_service.mock_confirm_payment(order):
            return redirect("storefront:order_payment", ref=ref)

        return redirect("storefront:order_tracking", ref=ref)


def _is_digital_payment(order) -> bool:
    payment = (order.data or {}).get("payment") or {}
    return str(payment.get("method") or "").lower() in {"pix", "card"}
