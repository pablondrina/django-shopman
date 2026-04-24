"""KDS — Kitchen Display System views.

GET views consume projections from ``shopman.shop.projections.kds``.
POST actions mutate state, then re-render via projection builders.
"""

from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from shopman.orderman.models import Order

from shopman.backstage.projections.kds import (
    build_kds_board,
    build_kds_index,
    build_kds_ticket,
)

logger = logging.getLogger(__name__)


PERM = "backstage.operate_kds"


def _perm_required(request):
    """Redirect to login if not staff; 403 if missing operate_kds perm."""
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect(f"/admin/login/?next={request.path}")
    if not request.user.has_perm(PERM):
        return HttpResponseForbidden("Você não tem permissão para esta ação.")
    return None


class KDSIndexView(View):
    """GET /kds/ — list active KDS instances."""

    def get(self, request: HttpRequest) -> HttpResponse:
        denied = _perm_required(request)
        if denied:
            return denied

        from shopman.shop.models import Shop
        instances = build_kds_index()
        shop = Shop.load()

        return render(request, "kds/index.html", {
            "instances": instances,
            "shop": shop,
        })


class KDSDisplayView(View):
    """GET /kds/<ref>/ — main KDS display for a specific instance."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _perm_required(request)
        if denied:
            return denied

        from shopman.shop.models import Shop

        from shopman.backstage.models import KDSInstance

        instance = get_object_or_404(KDSInstance, ref=ref, is_active=True)
        board = build_kds_board(ref)
        shop = Shop.load()

        return render(request, "kds/display.html", {
            "instance": instance,
            "board": board,
            "tickets": board.tickets,
            "is_expedition": board.is_expedition,
            "shop": shop,
        })


class KDSTicketListPartialView(View):
    """HTMX partial: ticket grid for polling updates."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _perm_required(request)
        if denied:
            return denied

        from shopman.backstage.models import KDSInstance

        instance = get_object_or_404(KDSInstance, ref=ref, is_active=True)
        board = build_kds_board(ref)

        return render(request, "kds/partials/ticket_list.html", {
            "tickets": board.tickets,
            "instance": instance,
            "is_expedition": board.is_expedition,
        })


class KDSTicketCheckItemView(View):
    """POST /kds/ticket/<pk>/check/ — toggle item checkbox."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        denied = _perm_required(request)
        if denied:
            return denied

        from shopman.backstage.models import KDSTicket

        ticket = get_object_or_404(KDSTicket, pk=pk)
        index = int(request.POST.get("index", 0))

        if 0 <= index < len(ticket.items):
            ticket.items[index]["checked"] = not ticket.items[index].get("checked", False)

            if ticket.status == "pending" and any(it.get("checked") for it in ticket.items):
                ticket.status = "in_progress"

            ticket.save(update_fields=["items", "status"])

            # When KDS operator starts working on a ticket, advance order
            # from "confirmed" → "preparing" (captures real prep start time).
            order = ticket.order
            if order.status == "confirmed" and order.can_transition_to("preparing"):
                order.transition_status("preparing", actor=f"kds:{request.user.username}")

        proj = build_kds_ticket(ticket.pk)
        return render(request, "kds/partials/ticket.html", {
            "t": proj,
            "instance": ticket.kds_instance,
            "is_expedition": False,
        })


class KDSTicketDoneView(View):
    """POST /kds/ticket/<pk>/done/ — mark ticket as done."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        denied = _perm_required(request)
        if denied:
            return denied

        from shopman.orderman.exceptions import InvalidTransition

        from shopman.backstage.models import KDSTicket

        ticket = get_object_or_404(KDSTicket, pk=pk)

        for item in ticket.items:
            item["checked"] = True
        ticket.status = "done"
        ticket.completed_at = timezone.now()
        ticket.save(update_fields=["items", "status", "completed_at"])

        logger.info("kds_done ticket=%d order=%s", ticket.pk, ticket.order.ref)

        order = ticket.order
        pending_tickets = order.kds_tickets.exclude(status="done").count()
        if pending_tickets == 0 and order.can_transition_to("ready"):
            try:
                order.transition_status("ready", actor="kds:auto")
                logger.info("kds_all_done order=%s → ready", order.ref)
            except InvalidTransition:
                pass

        return HttpResponse("")


class KDSExpeditionActionView(View):
    """POST /kds/expedition/<pk>/action/ — dispatch or complete order."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        denied = _perm_required(request)
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
