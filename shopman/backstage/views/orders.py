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
from shopman.orderman.models import Directive, Order

from shopman.backstage.projections.order_queue import (
    build_operator_order,
    build_order_card,
    build_order_queue,
    build_two_zone_queue,
)
from shopman.shop.services.cancellation import cancel

NOTIFICATION_SEND = "notification.send"

logger = logging.getLogger(__name__)


PERM = "shop.manage_orders"


def _get_order_or_err(request: HttpRequest, ref: str):
    """Return (order, None) on success, or (None, error_response) when not found.

    HTMX requests get an inline error card; full-page loads redirect to the queue.
    """
    try:
        return Order.objects.get(ref=ref), None
    except Order.DoesNotExist:
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
        if order.status != "new":
            return HttpResponse("Pedido não está aguardando confirmação", status=422)

        from shopman.shop.lifecycle import ensure_confirmable, ensure_payment_captured

        try:
            ensure_payment_captured(order)
            ensure_confirmable(order)
        except Exception as exc:
            logger.exception("ensure_confirmable failed for order %s", ref)
            return HttpResponse(str(exc), status=422)

        order.transition_status("confirmed", actor=f"operator:{request.user.username}")

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

        from shopman.backstage.projections.order_queue import _next_status
        next_status = _next_status(order)
        if not next_status:
            return HttpResponse("", status=422)

        order.transition_status(next_status, actor=f"operator:{request.user.username}")

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
        order.data["internal_notes"] = request.POST.get("notes", "")
        order.save(update_fields=["data", "updated_at"])

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

        payment_data = dict(order.data.get("payment", {}))
        if payment_data.get("marked_paid_by"):
            card = build_order_card(order)
            return render(request, "pedidos/partials/card.html", {"o": card})

        payment_data["marked_paid_by"] = request.user.username
        updated_data = dict(order.data)
        updated_data["payment"] = payment_data
        Order.objects.filter(pk=order.pk).update(data=updated_data)
        order.data = updated_data

        if order.status == "new":
            from shopman.shop.lifecycle import ensure_confirmable

            try:
                ensure_confirmable(order)
            except Exception as exc:
                logger.exception("ensure_confirmable failed for order %s in mark_paid", ref)
                return HttpResponse(str(exc), status=422)

            order.transition_status("confirmed", actor=f"operator:{request.user.username}")

        logger.info("mark_paid order=%s operator=%s", order.ref, request.user.username)

        from shopman.shop.lifecycle import dispatch
        dispatch(order, "on_paid")

        card = build_order_card(order)
        response = render(request, "pedidos/partials/card.html", {"o": card})
        response["HX-Trigger"] = json.dumps({"ped-toast-success": {"msg": f"Pagamento registrado — #{order.ref}", "sound": "success"}})
        return response


class AlertAcknowledgeView(View):
    """POST /pedidos/alerts/<pk>/ack/ — dismiss an operator alert."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        denied = _perm_required(request)
        if denied:
            return denied

        from shopman.backstage.models import OperatorAlert

        OperatorAlert.objects.filter(pk=pk).update(acknowledged=True)
        return HttpResponse("")
