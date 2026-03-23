from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views import View

from shopman.utils.monetary import format_money
from shopman.ordering.models import Order


STATUS_LABELS = {
    "new": "Recebido",
    "confirmed": "Confirmado",
    "processing": "Em Preparo",
    "ready": "Pronto",
    "dispatched": "Despachado",
    "delivered": "Entregue",
    "completed": "Concluído",
    "cancelled": "Cancelado",
    "returned": "Devolvido",
}

STATUS_COLORS = {
    "new": "bg-blue-100 text-blue-800",
    "confirmed": "bg-indigo-100 text-indigo-800",
    "processing": "bg-yellow-100 text-yellow-800",
    "ready": "bg-green-100 text-green-800",
    "dispatched": "bg-purple-100 text-purple-800",
    "delivered": "bg-teal-100 text-teal-800",
    "completed": "bg-green-200 text-green-900",
    "cancelled": "bg-red-100 text-red-800",
    "returned": "bg-gray-100 text-gray-800",
}


def _build_tracking_context(order: Order) -> dict:
    """Build shared context for tracking page and status partial."""
    events = order.events.order_by("seq")
    timeline = []
    for event in events:
        payload = event.payload or {}
        label = STATUS_LABELS.get(payload.get("new_status", ""), event.type)
        timeline.append({
            "label": label,
            "type": event.type,
            "timestamp": event.created_at,
            "payload": payload,
        })

    items = []
    for item in order.items.all():
        items.append({
            "sku": item.sku,
            "name": item.name or item.sku,
            "qty": item.qty,
            "unit_price_display": f"R$ {format_money(item.unit_price_q)}",
            "total_display": f"R$ {format_money(item.line_total_q)}",
        })

    return {
        "order": order,
        "status_label": STATUS_LABELS.get(order.status, order.status),
        "status_color": STATUS_COLORS.get(order.status, "bg-gray-100 text-gray-800"),
        "timeline": timeline,
        "items": items,
        "total_display": f"R$ {format_money(order.total_q)}",
    }


class OrderTrackingView(View):
    """Full order tracking page with HTMX polling for status updates."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = get_object_or_404(Order, ref=ref)
        ctx = _build_tracking_context(order)
        return render(request, "storefront/tracking.html", ctx)


class OrderStatusPartialView(View):
    """HTMX partial: returns status badge + timeline for polling."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = get_object_or_404(Order, ref=ref)
        ctx = _build_tracking_context(order)
        return render(request, "storefront/partials/order_status.html", ctx)
