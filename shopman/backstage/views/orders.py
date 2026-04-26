"""Operator order queue views.

Paths and templates may stay in Portuguese for product UX, but technical module
and class names follow the suite-wide English naming rule.

GET views consume projections from ``shopman.shop.projections.order_queue``.
POST actions mutate state, then re-render via projection builders.
"""
from __future__ import annotations

import json
import logging

from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View

from shopman.backstage.projections.order_queue import (
    build_operator_order,
    build_order_card,
    build_two_zone_queue,
)
from shopman.shop.services import operator_orders

logger = logging.getLogger(__name__)


PERM = "shop.manage_orders"


def _get_order_or_err(request: HttpRequest, ref: str):
    """Return (order, None) on success, or (None, error_response) when not found.

    HTMX requests get an inline error card; full-page loads redirect to the queue.
    """
    order = operator_orders.find_order(ref)
    if order is not None:
        return order, None
    if request.headers.get("HX-Request"):
        return None, HttpResponse(
            f'<div class="card p-3 flex items-center gap-2 border-l-4 border-l-danger">'
            f'<span class="material-symbols-rounded text-base text-danger" aria-hidden="true">error</span>'
            f'<span class="text-sm">Pedido <strong class="font-mono">#{ref}</strong> não encontrado</span>'
            f'</div>',
            status=404,
        )
    return None, redirect("backstage:gestor_pedidos")


def _perm_required(request):
    """Redirect to login if not staff; 403 if missing manage_orders perm."""
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect(f"/admin/login/?next={request.path}")
    if not request.user.has_perm(PERM):
        return HttpResponseForbidden("Você não tem permissão para esta ação.")
    return None


class OperatorOrdersView(View):
    """Main operator dashboard page."""

    def get(self, request: HttpRequest) -> HttpResponse:
        denied = _perm_required(request)
        if denied:
            return denied

        queue = build_two_zone_queue()

        from shopman.backstage.models import OperatorAlert
        from shopman.shop.models import Shop

        shop = Shop.load()
        alerts = list(OperatorAlert.objects.filter(acknowledged=False)[:10])

        return render(request, "pedidos/index.html", {
            "queue": queue,
            "shop": shop,
            "alerts": alerts,
        })


class OrderListPartialView(View):
    """HTMX partial: returns order grid for polling updates."""

    def get(self, request: HttpRequest) -> HttpResponse:
        denied = _perm_required(request)
        if denied:
            return denied

        queue = build_two_zone_queue()

        return render(request, "pedidos/partials/order_list.html", {
            "queue": queue,
        })


class OrderDetailPartialView(View):
    """HTMX partial: expanded detail for a single order card."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _perm_required(request)
        if denied:
            return denied

        order, err = _get_order_or_err(request, ref)
        if err:
            return err
        detail = build_operator_order(order)

        return render(request, "pedidos/partials/detail.html", {
            "detail": detail,
            "items": detail.items,
            "timeline": detail.timeline,
            "internal_notes": detail.internal_notes,
        })


class OrderConfirmView(View):
    """POST /pedidos/<ref>/confirm/ — confirm an order."""

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _perm_required(request)
        if denied:
            return denied

        order, err = _get_order_or_err(request, ref)
        if err:
            return err
        try:
            operator_orders.confirm_order(order, actor=f"operator:{request.user.username}")
        except Exception as exc:
            logger.exception("ensure_confirmable failed for order %s", ref)
            return HttpResponse(str(exc), status=422)

        card = build_order_card(order)
        response = render(request, "pedidos/partials/card.html", {"o": card})
        response["HX-Trigger"] = json.dumps({"ped-toast-success": {"msg": f"Pedido #{ref} confirmado", "sound": "success"}})
        return response


class OrderRejectView(View):
    """POST /pedidos/<ref>/reject/ — operador recusa o pedido (motivo obrigatório)."""

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _perm_required(request)
        if denied:
            return denied

        reason = request.POST.get("reason", "").strip()
        if not reason:
            return HttpResponse("Motivo obrigatório", status=422)

        order, err = _get_order_or_err(request, ref)
        if err:
            return err
        operator_orders.reject_order(
            order,
            reason=reason,
            actor=f"operator:{request.user.username}",
            rejected_by=request.user.username,
        )

        response = render(request, "pedidos/partials/card_rejected.html", {"ref": order.ref})
        response["HX-Trigger"] = json.dumps({"ped-toast-success": {"msg": f"Pedido #{order.ref} rejeitado", "sound": "reject"}})
        return response


class OrderAdvanceView(View):
    """POST /pedidos/<ref>/advance/ — advance to next status."""

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _perm_required(request)
        if denied:
            return denied

        order, err = _get_order_or_err(request, ref)
        if err:
            return err

        try:
            operator_orders.advance_order(order, actor=f"operator:{request.user.username}")
        except ValueError:
            return HttpResponse("", status=422)

        card = build_order_card(order)
        response = render(request, "pedidos/partials/card.html", {"o": card})
        response["HX-Trigger"] = json.dumps({"ped-toast-success": {"msg": f"Pedido #{ref}: {card.status_label}", "sound": "success"}})
        return response


class OrderNotesView(View):
    """POST /pedidos/<ref>/notes/ — save internal notes."""

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _perm_required(request)
        if denied:
            return denied

        order, err = _get_order_or_err(request, ref)
        if err:
            return err
        operator_orders.save_internal_notes(order, notes=request.POST.get("notes", ""))

        now = timezone.localtime(timezone.now()).strftime("%H:%M")
        return HttpResponse(
            f'<span class="text-xs text-success flex items-center gap-1">'
            f'<span class="material-symbols-rounded text-base" aria-hidden="true">check</span>'
            f'Salvo às {now}</span>'
        )


class OrderMarkPaidView(View):
    """POST /pedidos/<ref>/mark-paid/ — operador confirma recebimento manual (dinheiro/cash)."""

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _perm_required(request)
        if denied:
            return denied

        order, err = _get_order_or_err(request, ref)
        if err:
            return err

        try:
            changed = operator_orders.mark_paid(
                order,
                actor=f"operator:{request.user.username}",
                operator_username=request.user.username,
            )
        except Exception as exc:
            logger.exception("mark_paid failed for order %s", ref)
            return HttpResponse(str(exc), status=422)

        if not changed:
            card = build_order_card(order)
            return render(request, "pedidos/partials/card.html", {"o": card})

        card = build_order_card(order)
        response = render(request, "pedidos/partials/card.html", {"o": card})
        response["HX-Trigger"] = json.dumps({"ped-toast-success": {"msg": f"Pagamento registrado — #{order.ref}", "sound": "success"}})
        return response


class OrderHistoricoView(View):
    """GET /gestor/pedidos/historico/ — recent completed/delivered/cancelled orders."""

    def get(self, request: HttpRequest) -> HttpResponse:
        denied = _perm_required(request)
        if denied:
            return denied

        orders = operator_orders.recent_history(limit=20)
        cards = [build_order_card(o) for o in orders]
        return render(request, "pedidos/historico.html", {"orders": cards})


class AlertAcknowledgeView(View):
    """POST /pedidos/alerts/<pk>/ack/ — dismiss an operator alert."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        denied = _perm_required(request)
        if denied:
            return denied

        from shopman.backstage.models import OperatorAlert

        OperatorAlert.objects.filter(pk=pk).update(acknowledged=True)
        return HttpResponse("")
