from __future__ import annotations

import logging

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from shopman.orderman.models import Order

from shopman.shop.services import payment as payment_svc

logger = logging.getLogger("shopman.storefront.views.payment")


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

    Uses PaymentService to transition intent through authorize → capture.
    """

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        # URL only registered in DEBUG mode (urls.py), but belt-and-suspenders:
        if not settings.DEBUG:
            raise Http404

        from shopman.payman import PaymentError, PaymentService

        order = get_object_or_404(Order, ref=ref)

        payment = order.data.get("payment", {})
        if payment_svc.get_payment_status(order) == "captured":
            return redirect("storefront:order_tracking", ref=ref)

        # Transition via PaymentService
        intent_ref = payment.get("intent_ref")
        if intent_ref:
            try:
                intent = PaymentService.get(intent_ref)
                if intent.status == "pending":
                    PaymentService.authorize(intent_ref, gateway_id=f"mock_confirm_{intent_ref}")
                if intent.status in ("pending", "authorized"):
                    PaymentService.capture(intent_ref)
            except PaymentError as exc:
                logger.warning(
                    "Mock payment transition failed: %s", exc,
                    extra={"intent_ref": intent_ref, "order_ref": ref},
                )

        # Record mock capture timestamp — Payman (PaymentService) is the canonical status source
        payment["captured_at"] = timezone.now().isoformat()
        order.data["payment"] = payment
        order.save(update_fields=["data", "updated_at"])

        # Emit payment event
        method = payment.get("method", "pix")
        order.emit_event(
            event_type="payment.captured",
            actor="mock_payment",
            payload={"method": method, "amount_q": payment.get("amount_q", order.total_q)},
        )

        # Transition to confirmed (if still new)
        if order.status == "new":
            from shopman.shop.lifecycle import ensure_confirmable

            ensure_confirmable(order)
            order.transition_status("confirmed", actor=f"payment.{method}")

        return redirect("storefront:order_tracking", ref=ref)
