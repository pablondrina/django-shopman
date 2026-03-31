from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.decorators.http import require_POST
from shopman.ordering.holds import release_holds_for_order
from shopman.ordering.models import Directive, Order
from shopman.utils.monetary import format_money

from ..cart import CartService
from ._helpers import _carrier_tracking_url, _format_opening_hours, _get_price_q

logger = logging.getLogger(__name__)

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
    "new": "bg-info-light text-info-foreground",
    "confirmed": "bg-info-light text-info-foreground",
    "processing": "bg-warning-light text-warning-foreground",
    "ready": "bg-success-light text-success-foreground",
    "dispatched": "bg-info-light text-info-foreground",
    "delivered": "bg-success-light text-success-foreground",
    "completed": "bg-success-light text-success-foreground",
    "cancelled": "bg-error-light text-error-foreground",
    "returned": "bg-muted text-muted-foreground",
}

FULFILLMENT_STATUS_LABELS = {
    "pending": "Aguardando",
    "in_progress": "Em separação",
    "dispatched": "Despachado",
    "delivered": "Entregue",
    "cancelled": "Cancelado",
}

# ── Event type labels (timeline) ──────────────────────────────────────
# Maps raw event types to human-readable Portuguese labels.
EVENT_LABELS = {
    # Order lifecycle
    "created": "Pedido criado",
    "status_changed": None,  # handled via STATUS_LABELS + payload.new_status
    # Payment
    "payment.captured": "Pagamento confirmado",
    "payment.refunded": "Pagamento estornado",
    # Returns
    "return_initiated": "Devolução solicitada",
    "refund_processed": "Reembolso processado",
    "fiscal_cancelled": "Nota fiscal cancelada",
    # Fulfillment (added inline, not via emit_event)
    "fulfillment.dispatched": "Pedido enviado",
    "fulfillment.delivered": "Pedido entregue",
}

# Statuses that allow customer self-cancellation
_CANCELLABLE_STATUSES = {Order.Status.NEW, Order.Status.CONFIRMED}
_TERMINAL_STATUSES = {"completed", "cancelled", "returned"}


def _pickup_info() -> dict | None:
    """Load store address and opening hours for pickup fulfillments."""
    try:
        from shop.models import Shop

        shop = Shop.load()
        if not shop:
            return None
        return {
            "address": shop.formatted_address or "",
            "opening_hours": _format_opening_hours(),
        }
    except Exception:
        return None


def _build_tracking_context(order: Order) -> dict:
    """Build shared context for tracking page and status partial."""
    events = order.events.order_by("seq")
    timeline = []
    for event in events:
        payload = event.payload or {}
        status_key = payload.get("new_status", "")

        # Resolve label: status_changed uses STATUS_LABELS, others use EVENT_LABELS
        if event.type == "status_changed" and status_key:
            label = STATUS_LABELS.get(status_key, status_key)
        else:
            label = EVENT_LABELS.get(event.type)
            if label is None:
                # Fallback: humanize the event type (payment.captured → Pagamento captured)
                label = event.type.replace(".", " ").replace("_", " ").title()

        timeline.append({
            "label": label,
            "type": event.type,
            "timestamp": event.created_at,
            "payload": payload,
            "icon": STATUS_ICONS.get(status_key, ""),
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

    # Fulfillment tracking data — split into delivery vs pickup lists
    delivery_fulfillments = []
    pickup_fulfillments = []
    for ful in order.fulfillments.all():
        tracking_url = ful.tracking_url or _carrier_tracking_url(ful.carrier, ful.tracking_code)
        entry = {
            "id": ful.pk,
            "status": ful.status,
            "status_label": FULFILLMENT_STATUS_LABELS.get(ful.status, ful.status),
            "tracking_code": ful.tracking_code,
            "tracking_url": tracking_url,
            "carrier": ful.carrier,
            "dispatched_at": ful.dispatched_at,
            "delivered_at": ful.delivered_at,
        }
        if ful.carrier or ful.tracking_code:
            delivery_fulfillments.append(entry)
        else:
            pickup_fulfillments.append(entry)

        # Merge fulfillment timestamps into timeline
        if ful.dispatched_at:
            timeline.append({
                "label": "Enviado",
                "type": "fulfillment.dispatched",
                "timestamp": ful.dispatched_at,
                "payload": {},
            })
        if ful.delivered_at:
            timeline.append({
                "label": "Entregue",
                "type": "fulfillment.delivered",
                "timestamp": ful.delivered_at,
                "payload": {},
            })

    # Sort timeline chronologically
    timeline.sort(key=lambda e: e["timestamp"])

    # Pickup info (store address + hours) only if needed
    pickup = _pickup_info() if pickup_fulfillments else None

    # Cancellation: allowed if NEW/CONFIRMED and payment not captured
    payment = order.data.get("payment", {})
    payment_captured = payment.get("status") == "captured"
    can_cancel = (
        order.status in _CANCELLABLE_STATUSES
        and not payment_captured
    )

    # Is order in an active (non-terminal) state?
    is_active = order.status not in _TERMINAL_STATUSES

    # Confirmation countdown (optimistic mode)
    confirmation_countdown = False
    confirmation_expires_at = None
    if order.status == "new":
        from channels.config import ChannelConfig
        config = ChannelConfig.effective(order.channel)
        if config.confirmation.mode == "optimistic":
            from datetime import timedelta
            confirmation_countdown = True
            confirmation_expires_at = order.created_at + timedelta(
                minutes=config.confirmation.timeout_minutes
            )

    # ETA for processing orders
    eta = None
    if order.status == "processing":
        from django.utils import timezone as tz
        from shop.models import Shop
        shop = Shop.load()
        prep_minutes = getattr(shop, "prep_time_minutes", None) or 30
        eta = tz.localtime(order.created_at) + tz.timedelta(minutes=prep_minutes)

    return {
        "order": order,
        "status_label": STATUS_LABELS.get(order.status, order.status),
        "status_color": STATUS_COLORS.get(order.status, "bg-muted text-muted-foreground"),
        "timeline": timeline,
        "items": items,
        "total_display": f"R$ {format_money(order.total_q)}",
        "delivery_fulfillments": delivery_fulfillments,
        "pickup_fulfillments": pickup_fulfillments,
        "pickup": pickup,
        "can_cancel": can_cancel,
        "is_active": is_active,
        "confirmation_countdown": confirmation_countdown,
        "confirmation_expires_at": confirmation_expires_at,
        "eta": eta,
    }


class OrderTrackingView(View):
    """Full order tracking page with HTMX polling for status updates."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = get_object_or_404(Order, ref=ref)
        ctx = _build_tracking_context(order)

        # WhatsApp contact URL (from Shop social links or phone)
        from shop.models import Shop
        shop = Shop.load()
        whatsapp_url = ""
        if shop:
            for link in (shop.social_links or []):
                if "wa.me" in link or "whatsapp.com" in link:
                    whatsapp_url = link
                    break
            if not whatsapp_url and shop.phone:
                digits = "".join(c for c in shop.phone if c.isdigit())
                whatsapp_url = f"https://wa.me/{digits}"

        # Share text
        share_text = f"Meu pedido {order.ref} na {shop.name if shop else 'loja'}"

        ctx["whatsapp_url"] = whatsapp_url
        ctx["share_text"] = share_text
        return render(request, "storefront/tracking.html", ctx)


STATUS_ICONS = {
    "new": '<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5 3a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2V5a2 2 0 00-2-2H5zm0 2h10v7h-2l-1 2H8l-1-2H5V5z" clip-rule="evenodd"/></svg>',
    "confirmed": '<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>',
    "processing": '<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"/></svg>',
    "ready": '<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/></svg>',
    "dispatched": '<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path d="M8 16.5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zM15 16.5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0z"/><path d="M0 4a1 1 0 011-1h11a1 1 0 011 1v1h2.38l2.45 3.26A1 1 0 0118 9v3a1 1 0 01-1 1h-1.05a2.5 2.5 0 00-4.9 0H8.95a2.5 2.5 0 00-4.9 0H3a1 1 0 01-1-1V5H1a1 1 0 01-1-1z"/></svg>',
    "delivered": '<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path d="M10.707 2.293a1 1 0 00-1.414 0l-7 7a1 1 0 001.414 1.414L4 10.414V17a1 1 0 001 1h2a1 1 0 001-1v-2a1 1 0 011-1h2a1 1 0 011 1v2a1 1 0 001 1h2a1 1 0 001-1v-6.586l.293.293a1 1 0 001.414-1.414l-7-7z"/></svg>',
    "completed": '<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/></svg>',
    "cancelled": '<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/></svg>',
}


class ReorderView(View):
    """POST: re-add all items from a past order to the cart."""

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        from django.shortcuts import redirect
        from shopman.offering.models import Product

        order = get_object_or_404(Order, ref=ref)
        for item in order.items.all():
            product = Product.objects.filter(sku=item.sku, is_published=True).first()
            if product and product.is_available:
                price_q = _get_price_q(product)
                if price_q is None:
                    price_q = 0
                CartService.add_item(request, sku=item.sku, qty=int(item.qty), unit_price_q=price_q)

        return redirect("storefront:cart")


class OrderStatusPartialView(View):
    """HTMX partial: returns status badge + timeline for polling."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = get_object_or_404(Order, ref=ref)
        ctx = _build_tracking_context(order)
        response = render(request, "storefront/partials/order_status.html", ctx)
        # Stop HTMX polling on terminal status by setting code 286
        if order.status in _TERMINAL_STATUSES:
            response.status_code = 286
        return response


class OrderCancelView(View):
    """Customer self-service cancellation from tracking page."""

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        from channels.topics import NOTIFICATION_SEND

        order = get_object_or_404(Order, ref=ref)

        # Only cancellable if NEW or CONFIRMED and payment not captured
        payment_status = order.data.get("payment", {}).get("status", "")
        if order.status not in _CANCELLABLE_STATUSES:
            if request.headers.get("HX-Request"):
                return HttpResponse(
                    '<div class="toast toast-error" role="alert" aria-live="assertive">'
                    "Não é possível cancelar este pedido no status atual.</div>",
                    status=422,
                )
            return redirect("storefront:order_tracking", ref=ref)

        if payment_status == "captured":
            if request.headers.get("HX-Request"):
                return HttpResponse(
                    '<div class="toast toast-warning" role="alert" aria-live="assertive">'
                    "Pagamento já confirmado. Entre em contato para cancelar.</div>",
                    status=422,
                )
            return redirect("storefront:order_tracking", ref=ref)

        # Cancel the order
        order.transition_status(Order.Status.CANCELLED, actor="customer.self_cancel")
        order.data["cancellation_reason"] = "customer_requested"
        order.save(update_fields=["data", "updated_at"])

        # Release holds
        release_holds_for_order(order)

        # Notify operator
        Directive.objects.create(
            topic=NOTIFICATION_SEND,
            payload={
                "order_ref": order.ref,
                "template": "order_cancelled_by_customer",
            },
        )

        logger.info("customer_self_cancel order=%s", order.ref)

        if request.headers.get("HX-Request"):
            ctx = _build_tracking_context(order)
            return render(request, "storefront/partials/order_status.html", ctx)
        return redirect("storefront:order_tracking", ref=ref)
