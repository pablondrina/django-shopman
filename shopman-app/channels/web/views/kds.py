"""KDS — Kitchen Display System views."""

from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from shopman.ordering.models import Order
from shopman.utils.monetary import format_money

from .pedidos import CHANNEL_BADGES

logger = logging.getLogger(__name__)


def _staff_required(request):
    """Check staff auth; return redirect response or None."""
    if not request.user.is_staff:
        return redirect(f"/admin/login/?next={request.path}")
    return None


def _enrich_ticket(ticket, instance) -> dict:
    """Build template-ready dict for a KDS ticket card."""
    now = timezone.now()
    elapsed = (now - ticket.created_at).total_seconds()
    target_sec = instance.target_time_minutes * 60

    if elapsed < target_sec:
        timer_class = "timer-ok"
    elif elapsed < target_sec * 2:
        timer_class = "timer-warning"
    else:
        timer_class = "timer-late"

    order = ticket.order
    customer_name = order.data.get("customer_name", "") or order.handle_ref or ""
    delivery_method = order.data.get("delivery_method", "")
    fulfillment_icon = "\U0001f697" if delivery_method == "delivery" else "\U0001f3ea"

    return {
        "pk": ticket.pk,
        "order_ref": order.ref,
        "channel_badge": CHANNEL_BADGES.get(
            order.channel.ref if order.channel_id else "", "\U0001f4e6"
        ),
        "customer_name": customer_name,
        "fulfillment_icon": fulfillment_icon,
        "created_at": ticket.created_at,
        "elapsed_seconds": int(elapsed),
        "timer_class": timer_class,
        "items": ticket.items,
        "status": ticket.status,
        "ticket": ticket,
    }


def _enrich_expedition_order(order) -> dict:
    """Build template-ready dict for an expedition order card."""
    customer_name = order.data.get("customer_name", "") or order.handle_ref or ""
    delivery_method = order.data.get("delivery_method", "")
    is_delivery = delivery_method == "delivery"

    return {
        "pk": order.pk,
        "ref": order.ref,
        "channel_badge": CHANNEL_BADGES.get(
            order.channel.ref if order.channel_id else "", "\U0001f4e6"
        ),
        "customer_name": customer_name,
        "fulfillment_icon": "\U0001f697" if is_delivery else "\U0001f3ea",
        "fulfillment_label": "Delivery" if is_delivery else "Retirada",
        "is_delivery": is_delivery,
        "items_count": order.items.count(),
        "total_display": f"R$ {format_money(order.total_q)}",
        "order": order,
    }


class KDSIndexView(View):
    """GET /kds/ — list active KDS instances."""

    def get(self, request: HttpRequest) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        from shop.models import KDSInstance, KDSTicket, Shop

        instances = KDSInstance.objects.filter(is_active=True).order_by("name")

        # Annotate with pending ticket count
        enriched = []
        for inst in instances:
            if inst.type == "expedition":
                count = Order.objects.filter(status="ready").count()
            else:
                count = KDSTicket.objects.filter(
                    kds_instance=inst, status__in=["pending", "in_progress"],
                ).count()
            enriched.append({
                "instance": inst,
                "pending_count": count,
            })

        shop = Shop.load()
        return render(request, "kds/index.html", {
            "instances": enriched,
            "shop": shop,
        })


class KDSDisplayView(View):
    """GET /kds/<ref>/ — main KDS display for a specific instance."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        from shop.models import KDSInstance, KDSTicket, Shop

        instance = get_object_or_404(KDSInstance, ref=ref, is_active=True)
        shop = Shop.load()

        if instance.type == "expedition":
            orders = (
                Order.objects.filter(status="ready")
                .select_related("channel")
                .order_by("created_at")
            )
            enriched = [_enrich_expedition_order(o) for o in orders]
            return render(request, "kds/display.html", {
                "instance": instance,
                "tickets": enriched,
                "is_expedition": True,
                "shop": shop,
            })

        tickets = (
            KDSTicket.objects.filter(
                kds_instance=instance, status__in=["pending", "in_progress"],
            )
            .select_related("order", "order__channel")
            .order_by("created_at")
        )
        enriched = [_enrich_ticket(t, instance) for t in tickets]

        return render(request, "kds/display.html", {
            "instance": instance,
            "tickets": enriched,
            "is_expedition": False,
            "shop": shop,
        })


class KDSTicketListPartialView(View):
    """HTMX partial: ticket grid for polling updates."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        from shop.models import KDSInstance, KDSTicket

        instance = get_object_or_404(KDSInstance, ref=ref, is_active=True)

        if instance.type == "expedition":
            orders = (
                Order.objects.filter(status="ready")
                .select_related("channel")
                .order_by("created_at")
            )
            enriched = [_enrich_expedition_order(o) for o in orders]
        else:
            tickets = (
                KDSTicket.objects.filter(
                    kds_instance=instance, status__in=["pending", "in_progress"],
                )
                .select_related("order", "order__channel")
                .order_by("created_at")
            )
            enriched = [_enrich_ticket(t, instance) for t in tickets]

        return render(request, "kds/partials/ticket_list.html", {
            "tickets": enriched,
            "instance": instance,
            "is_expedition": instance.type == "expedition",
        })


class KDSTicketCheckItemView(View):
    """POST /kds/ticket/<pk>/check/ — toggle item checkbox."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        from shop.models import KDSTicket

        ticket = get_object_or_404(KDSTicket, pk=pk)
        index = int(request.POST.get("index", 0))

        if 0 <= index < len(ticket.items):
            ticket.items[index]["checked"] = not ticket.items[index].get("checked", False)

            # If any item is checked, move to in_progress
            if ticket.status == "pending" and any(it.get("checked") for it in ticket.items):
                ticket.status = "in_progress"

            ticket.save(update_fields=["items", "status"])

        instance = ticket.kds_instance
        enriched = _enrich_ticket(ticket, instance)
        return render(request, "kds/partials/ticket.html", {
            "t": enriched,
            "instance": instance,
            "is_expedition": False,
        })


class KDSTicketDoneView(View):
    """POST /kds/ticket/<pk>/done/ — mark ticket as done."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        from shopman.ordering.exceptions import InvalidTransition

        from shop.models import KDSTicket

        ticket = get_object_or_404(KDSTicket, pk=pk)

        # Mark all items checked + ticket done
        for item in ticket.items:
            item["checked"] = True
        ticket.status = "done"
        ticket.completed_at = timezone.now()
        ticket.save(update_fields=["items", "status", "completed_at"])

        logger.info("kds_done ticket=%d order=%s", ticket.pk, ticket.order.ref)

        # Check if ALL tickets for this order are done → advance to READY
        order = ticket.order
        pending_tickets = order.kds_tickets.exclude(status="done").count()
        if pending_tickets == 0 and order.can_transition_to("ready"):
            try:
                order.transition_status("ready", actor="kds:auto")
                logger.info("kds_all_done order=%s → ready", order.ref)
            except InvalidTransition:
                # Race condition: another KDS station already advanced
                pass

        return HttpResponse("")


class KDSExpeditionActionView(View):
    """POST /kds/expedition/<pk>/action/ — dispatch or complete order."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        order = get_object_or_404(Order, pk=pk)
        action = request.POST.get("action", "")
        actor = f"kds:{request.user.username}"

        if action == "dispatch" and order.can_transition_to("dispatched"):
            order.transition_status("dispatched", actor=actor)
            logger.info("kds_expedition dispatch order=%s", order.ref)
        elif action == "complete" and order.can_transition_to("completed"):
            order.transition_status("completed", actor=actor)
            logger.info("kds_expedition complete order=%s", order.ref)
        else:
            return HttpResponse("Ação inválida", status=422)

        return HttpResponse("")
