"""Gestor de pedidos (operador) — fila de orders do canal; URLs em /pedidos/.

Nomes em português no path são de domínio (cardápio, pedido). As classes usam
inglês (Order) onde o código já padronizou assim.
"""
from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from shopman.omniman.models import Directive, Order
from shopman.services.cancellation import cancel
from shopman.utils.monetary import format_money

from .tracking import STATUS_COLORS, STATUS_LABELS, _build_tracking_context

NOTIFICATION_SEND = "notification.send"

logger = logging.getLogger(__name__)

# ── Channel badge mapping ────────────────────────────────────────────

# Material Symbols Rounded — ligature names por canal
CHANNEL_ICONS = {
    "web": "language",
    "whatsapp": "chat",
    "ifood": "fastfood",
    "pos": "storefront",
}
_DEFAULT_CHANNEL_ICON = "shopping_bag"

# ── Action labels per status ─────────────────────────────────────────

NEXT_STATUS_MAP = {
    "confirmed": "preparing",
    "preparing": "ready",
    "ready": "completed",
    "dispatched": "delivered",
    "delivered": "completed",
}

NEXT_ACTION_LABELS = {
    "confirmed": "Iniciar Preparo \u25b8",
    "preparing": "Marcar Pronto \u25b8",
    "ready": "Entregar \u2713",  # pickup default; delivery override in _enrich_order
    "dispatched": "Marcar Entregue \u2713",
    "delivered": "Concluir \u2713",
}

# Delivery-specific label override for "ready" status
READY_DELIVERY_LABEL = "Saiu para Entrega \u25b8"


def _is_delivery(order) -> bool:
    """True if this order is for delivery (not pickup/balcão).

    Uses canonical key fulfillment_type with fallback to legacy delivery_method.
    """
    ft = order.data.get("fulfillment_type") or order.data.get("delivery_method", "")
    return ft == "delivery"


def _next_status_for(order) -> str:
    """Next status for UX routing.

    For delivery orders: ready → dispatched.
    For pickup orders: ready → completed.
    The Kernel enforces the dispatched-requires-delivery invariant as a safety net.
    """
    if order.status == "ready" and _is_delivery(order):
        return "dispatched"
    return NEXT_STATUS_MAP.get(order.status, "")


def _next_label_for(order) -> str:
    """Next action label considering delivery lifecycle."""
    if order.status == "ready" and _is_delivery(order):
        return READY_DELIVERY_LABEL
    return NEXT_ACTION_LABELS.get(order.status, "")

# ── Active statuses for the gestor ───────────────────────────────────

_ACTIVE_STATUSES = ["new", "confirmed", "preparing", "ready", "dispatched", "delivered"]


def _staff_required(request):
    """Check staff auth; return redirect response or None."""
    if not request.user.is_staff:
        return redirect(f"/admin/login/?next={request.path}")
    return None


def _enrich_order(order: Order) -> dict:
    """Build template-ready dict for a single order card."""
    now = timezone.now()
    elapsed = (now - order.created_at).total_seconds()

    # Timer class for new orders (confirmation urgency)
    if order.status == "new":
        if elapsed < 180:
            timer_class = "timer-ok"
        elif elapsed < 240:
            timer_class = "timer-warning"
        else:
            timer_class = "timer-urgent"
    else:
        timer_class = "timer-muted"

    # Items summary (first 3 items)
    items = list(order.items.all()[:4])
    items_summary = ", ".join(
        f"{int(it.qty)}x {it.name or it.sku}" for it in items[:3]
    )
    if len(items) > 3:
        items_summary += "..."

    items_count = order.items.count()

    delivery_method = order.data.get("delivery_method", "")
    if delivery_method == "delivery":
        fulfillment_icon = "local_shipping"
        fulfillment_label = "Delivery"
    else:
        fulfillment_icon = "storefront"
        fulfillment_label = "Retirada"

    # Customer name
    customer_name = order.data.get("customer_name", "") or order.handle_ref or ""

    return {
        "id": order.pk,
        "ref": order.ref,
        "status": order.status,
        "status_label": STATUS_LABELS.get(order.status, order.status),
        "status_color": STATUS_COLORS.get(order.status, "bg-muted text-muted-foreground"),
        "channel_ref": order.channel.ref if order.channel_id else "",
        "channel_icon": CHANNEL_ICONS.get(
            order.channel.ref if order.channel_id else "", _DEFAULT_CHANNEL_ICON
        ),
        "customer_name": customer_name,
        "created_at": order.created_at,
        "elapsed_seconds": int(elapsed),
        "timer_class": timer_class,
        "items_summary": items_summary,
        "items_count": items_count,
        "total_display": f"R$ {format_money(order.total_q)}",
        "fulfillment_icon": fulfillment_icon,
        "fulfillment_label": fulfillment_label,
        "can_confirm": order.status == "new",
        "can_advance": order.status in ("confirmed", "preparing", "ready", "dispatched", "delivered"),
        "next_status": _next_status_for(order),
        "next_action_label": _next_label_for(order),
        "order": order,
        "payment_method": order.data.get("payment", {}).get("method", ""),
        "payment_status": order.data.get("payment", {}).get("status", ""),
    }


def _status_counts(orders) -> dict:
    """Count orders per status for the filter pills."""
    counts = dict.fromkeys(_ACTIVE_STATUSES, 0)
    for order in orders:
        if order.status in counts:
            counts[order.status] += 1
    counts["all"] = sum(counts.values())
    return counts


def _get_filtered_orders(filter_status: str):
    """Return filtered queryset of active orders."""
    qs = Order.objects.filter(
        status__in=_ACTIVE_STATUSES,
    ).select_related("channel").order_by("created_at")

    if filter_status and filter_status != "all" and filter_status in _ACTIVE_STATUSES:
        qs = qs.filter(status=filter_status)

    return qs


class GestorPedidosView(View):
    """Main operator dashboard page."""

    def get(self, request: HttpRequest) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        all_orders = Order.objects.filter(
            status__in=_ACTIVE_STATUSES,
        ).select_related("channel").order_by("created_at")

        filter_status = request.GET.get("filter", "all")
        if filter_status != "all" and filter_status in _ACTIVE_STATUSES:
            orders = all_orders.filter(status=filter_status)
        else:
            orders = all_orders

        enriched = [_enrich_order(o) for o in orders]
        counts = _status_counts(all_orders)

        from shopman.models import Shop
        shop = Shop.load()

        return render(request, "pedidos/index.html", {
            "orders": enriched,
            "counts": counts,
            "filter": filter_status,
            "shop": shop,
        })


class OrderListPartialView(View):
    """HTMX partial: returns order grid for polling updates."""

    def get(self, request: HttpRequest) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        all_orders = Order.objects.filter(
            status__in=_ACTIVE_STATUSES,
        ).select_related("channel").order_by("created_at")

        filter_status = request.GET.get("filter", "all")
        if filter_status != "all" and filter_status in _ACTIVE_STATUSES:
            orders = all_orders.filter(status=filter_status)
        else:
            orders = all_orders

        enriched = [_enrich_order(o) for o in orders]
        counts = _status_counts(all_orders)

        return render(request, "pedidos/partials/order_list.html", {
            "orders": enriched,
            "counts": counts,
            "filter": filter_status,
        })


class PedidoDetailPartialView(View):
    """HTMX partial: expanded detail for a single order card."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        order = get_object_or_404(Order, ref=ref)

        # Items with full detail
        items = []
        for item in order.items.all():
            items.append({
                "sku": item.sku,
                "name": item.name or item.sku,
                "qty": int(item.qty),
                "unit_price_display": f"R$ {format_money(item.unit_price_q)}",
                "total_display": f"R$ {format_money(item.line_total_q)}",
            })

        # Mini timeline
        ctx = _build_tracking_context(order)

        return render(request, "pedidos/partials/detail.html", {
            "order": order,
            "items": items,
            "timeline": ctx["timeline"],
            "internal_notes": order.data.get("internal_notes", ""),
        })


class PedidoConfirmView(View):
    """POST /pedidos/<ref>/confirm/ — confirm an order."""

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        order = get_object_or_404(Order, ref=ref)
        if order.status != "new":
            return HttpResponse("Pedido não está aguardando confirmação", status=422)

        order.transition_status("confirmed", actor=f"operator:{request.user.username}")

        enriched = _enrich_order(order)
        return render(request, "pedidos/partials/card.html", {"o": enriched})


class GestorOrderRejectView(View):
    """POST /pedidos/<ref>/reject/ — operador recusa o pedido (motivo obrigatório)."""

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        reason = request.POST.get("reason", "").strip()
        if not reason:
            return HttpResponse("Motivo obrigatório", status=422)

        order = get_object_or_404(Order, ref=ref)
        cancel(
            order,
            reason=reason,
            actor=f"operator:{request.user.username}",
            extra_data={"rejected_by": request.user.username},
        )

        Directive.objects.create(
            topic=NOTIFICATION_SEND,
            payload={
                "order_ref": order.ref,
                "template": "order_rejected",
                "reason": reason,
            },
        )

        logger.info("operator_reject order=%s reason=%s", order.ref, reason)

        # Return empty to remove card from grid
        return HttpResponse("")


class PedidoAdvanceView(View):
    """POST /pedidos/<ref>/advance/ — advance to next status."""

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        order = get_object_or_404(Order, ref=ref)

        # Delivery-aware next status (ready → dispatched for delivery orders)
        next_status = _next_status_for(order)
        if not next_status:
            return HttpResponse("", status=422)

        order.transition_status(next_status, actor=f"operator:{request.user.username}")

        enriched = _enrich_order(order)
        return render(request, "pedidos/partials/card.html", {"o": enriched})


class PedidoNotesView(View):
    """POST /pedidos/<ref>/notes/ — save internal notes."""

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        order = get_object_or_404(Order, ref=ref)
        order.data["internal_notes"] = request.POST.get("notes", "")
        order.save(update_fields=["data", "updated_at"])

        return HttpResponse('<span class="ped-notes-saved">Salvo</span>')


class PedidoMarkPaidView(View):
    """POST /pedidos/<ref>/mark-paid/ — operador confirma recebimento manual (dinheiro/counter)."""

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        order = get_object_or_404(Order, ref=ref)

        payment_data = order.data.get("payment", {})
        if payment_data.get("status") == "captured":
            # Already marked — idempotent, return updated card
            enriched = _enrich_order(order)
            return render(request, "pedidos/partials/card.html", {"o": enriched})

        payment_data["status"] = "captured"
        payment_data["marked_paid_by"] = request.user.username
        order.data["payment"] = payment_data
        order.save(update_fields=["data", "updated_at"])

        if order.status == "new":
            order.transition_status("confirmed", actor=f"operator:{request.user.username}")

        logger.info("mark_paid order=%s operator=%s", order.ref, request.user.username)

        from shopman.flows import dispatch
        dispatch(order, "on_paid")

        enriched = _enrich_order(order)
        return render(request, "pedidos/partials/card.html", {"o": enriched})
