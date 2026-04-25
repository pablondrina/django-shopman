"""KDS — Kitchen Display System views.

GET views consume projections from ``shopman.shop.projections.kds``.
POST actions mutate state, then re-render via projection builders.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from shopman.orderman.models import Order

from shopman.backstage.projections.kds import (
    build_kds_board,
    build_kds_index,
    build_kds_ticket,
)
from shopman.shop.services import kds as kds_service

PERM = "backstage.operate_kds"


def _staff_required(request):
    """Redirect to login if not authenticated+staff. No perm check."""
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect(f"/admin/login/?next={request.path}")
    return None


def _perm_required(request):
    """Redirect to login if not staff; 403 if missing operate_kds perm."""
    denied = _staff_required(request)
    if denied:
        return denied
    if not request.user.has_perm(PERM):
        return HttpResponseForbidden("Você não tem permissão para esta ação.")
    return None


class KDSIndexView(View):
    """GET /kds/ — list active KDS instances. Staff can view; only editors can interact."""

    def get(self, request: HttpRequest) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        from shopman.shop.models import Shop
        instances = build_kds_index()
        shop = Shop.load()
        is_readonly = not request.user.has_perm(PERM)

        return render(request, "kds/index.html", {
            "instances": instances,
            "shop": shop,
            "is_readonly": is_readonly,
        })


class KDSDisplayView(View):
    """GET /kds/<ref>/ — main KDS display. Staff can view; only editors can interact."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        from shopman.backstage.models import KDSInstance
        from shopman.shop.models import Shop

        instance = get_object_or_404(KDSInstance, ref=ref, is_active=True)
        board = build_kds_board(ref)
        shop = Shop.load()
        is_readonly = not request.user.has_perm(PERM)

        return render(request, "kds/display.html", {
            "instance": instance,
            "board": board,
            "tickets": board.tickets,
            "is_expedition": board.is_expedition,
            "shop": shop,
            "is_readonly": is_readonly,
        })


class KDSTicketListPartialView(View):
    """HTMX partial: ticket grid for polling updates."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        from shopman.backstage.models import KDSInstance

        instance = get_object_or_404(KDSInstance, ref=ref, is_active=True)
        board = build_kds_board(ref)
        is_readonly = not request.user.has_perm(PERM)

        return render(request, "kds/partials/ticket_list.html", {
            "tickets": board.tickets,
            "instance": instance,
            "is_expedition": board.is_expedition,
            "is_readonly": is_readonly,
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

        kds_service.toggle_ticket_item(
            ticket,
            index=index,
            actor=f"kds:{request.user.username}",
        )

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

        from shopman.backstage.models import KDSTicket

        ticket = get_object_or_404(KDSTicket, pk=pk)
        kds_service.complete_ticket(ticket, actor=f"kds:{request.user.username}")

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

        try:
            kds_service.expedition_action(order, action=action, actor=actor)
        except ValueError:
            return HttpResponse("Ação inválida", status=422)

        return HttpResponse("")
