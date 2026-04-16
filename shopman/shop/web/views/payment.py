from __future__ import annotations

import logging

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from shopman.orderman.models import Order
from shopman.utils.monetary import format_money

from shopman.shop.services import payment as payment_svc

from ._helpers import _is_v2_request

logger = logging.getLogger("shopman.shop.web.payment")


class PaymentView(View):
    """Payment page — PIX (QR code) or Card (Stripe Elements)."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = get_object_or_404(Order, ref=ref)
        payment = order.data.get("payment", {})
        method = payment.get("method", "pix")

        # If already paid, redirect to tracking
        if payment_svc.get_payment_status(order) == "captured":
            return redirect("storefront:order_tracking", ref=ref)

        # If order is cancelled, redirect to tracking (shows cancelled state)
        if order.status == "cancelled":
            return redirect("storefront:order_tracking", ref=ref)

        if _is_v2_request(request):
            from shopman.shop.projections import build_payment

            proj = build_payment(order)
            return render(request, "storefront/v2/payment.html", {"payment": proj})

        return render(request, "storefront/payment.html", {
            "order": order,
            "payment": payment,
            "method": method,
            "total_display": f"R$ {format_money(order.total_q)}",
            "debug": settings.DEBUG,
        })


class PaymentStatusView(View):
    """HTMX partial: polls payment status, redirects when paid."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = get_object_or_404(Order, ref=ref)

        if _is_v2_request(request):
            from shopman.shop.projections import build_payment_status

            proj = build_payment_status(order)
            if proj.is_paid:
                response = HttpResponse("")
                response["HX-Redirect"] = proj.redirect_url
                return response
            return render(request, "storefront/v2/partials/payment_status.html", {"payment_status": proj})

        payment = order.data.get("payment", {})

        is_paid = payment_svc.get_payment_status(order) == "captured"
        is_cancelled = order.status == "cancelled"

        # Check if PIX expired
        is_expired = False
        expires_at_str = payment.get("expires_at")
        if expires_at_str and not is_paid and not is_cancelled:
            from django.utils.dateparse import parse_datetime
            expires_at = parse_datetime(expires_at_str)
            if expires_at and timezone.now() > expires_at:
                is_expired = True

        if is_paid:
            # Payment confirmed — redirect to tracking
            response = HttpResponse("")
            response["HX-Redirect"] = f"/pedido/{order.ref}/"
            return response

        return render(request, "storefront/partials/payment_status.html", {
            "order": order,
            "payment": payment,
            "is_cancelled": is_cancelled,
            "is_expired": is_expired,
        })


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
