from __future__ import annotations

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from shopman.ordering.models import Order
from shopman.utils.monetary import format_money


class PaymentView(View):
    """PIX payment page — shows QR code, copy-paste code, and expiry timer."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = get_object_or_404(Order, ref=ref)
        payment = order.data.get("payment", {})

        return render(request, "storefront/payment.html", {
            "order": order,
            "payment": payment,
            "total_display": f"R$ {format_money(order.total_q)}",
        })


class PaymentStatusView(View):
    """HTMX partial: polls payment status, redirects when paid."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = get_object_or_404(Order, ref=ref)
        payment = order.data.get("payment", {})

        # Check PaymentService for real-time status
        intent_id = payment.get("intent_id")
        is_paid = payment.get("status") == "captured"

        if not is_paid and intent_id:
            from shopman.payments import PaymentError, PaymentService
            try:
                intent = PaymentService.get(intent_id)
                is_paid = intent.status == "captured"
            except PaymentError:
                pass

        is_cancelled = order.status == "cancelled"

        if is_paid:
            response = HttpResponse("")
            response["HX-Redirect"] = f"/pedido/{order.ref}/"
            return response

        return render(request, "storefront/partials/payment_status.html", {
            "order": order,
            "payment": payment,
            "is_cancelled": is_cancelled,
        })


class MockPaymentConfirmView(View):
    """
    DEV ONLY: Simulate PIX payment confirmation.

    Uses PaymentService to transition intent through authorize → capture.
    """

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        if not settings.DEBUG:
            raise Http404

        from shopman.payments import PaymentError, PaymentService

        order = get_object_or_404(Order, ref=ref)

        payment = order.data.get("payment", {})
        if payment.get("status") == "captured":
            return redirect("storefront:order_tracking", ref=ref)

        # Transition via PaymentService
        intent_id = payment.get("intent_id")
        if intent_id:
            try:
                intent = PaymentService.get(intent_id)
                if intent.status == "pending":
                    PaymentService.authorize(intent_id, gateway_id=f"mock_confirm_{intent_id}")
                if intent.status in ("pending", "authorized"):
                    PaymentService.capture(intent_id)
            except PaymentError:
                pass

        # Mark payment as captured in order data
        payment["status"] = "captured"
        payment["captured_at"] = timezone.now().isoformat()
        order.data["payment"] = payment
        order.save(update_fields=["data", "updated_at"])

        # Emit payment event
        order.emit_event(
            event_type="payment.captured",
            actor="mock_payment",
            payload={"method": "pix", "amount_q": payment.get("amount_q", order.total_q)},
        )

        # Transition to confirmed (if still new)
        if order.status == "new":
            order.transition_status("confirmed", actor="payment.pix")

        return redirect("storefront:order_tracking", ref=ref)
