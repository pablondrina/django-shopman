from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from shopman.utils.monetary import format_money
from shopman.ordering.models import Order


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

        # Check if payment was captured
        is_paid = payment.get("status") == "captured"
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

    Updates order.data["payment"]["status"] to "captured" and transitions
    the order to "confirmed". In production this would be a webhook from
    the payment gateway.
    """

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = get_object_or_404(Order, ref=ref)

        payment = order.data.get("payment", {})
        if payment.get("status") == "captured":
            # Already paid — redirect
            return redirect("storefront:order_tracking", ref=ref)

        # Mark payment as captured
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
