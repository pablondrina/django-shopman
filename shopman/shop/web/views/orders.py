"""Operator order queue views.

Paths and templates may stay in Portuguese for product UX, but technical module
and class names follow the suite-wide English naming rule.

GET views consume projections from ``shopman.shop.projections.order_queue``.
POST actions mutate state, then re-render via projection builders.
"""
from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from shopman.orderman.models import Directive, Order

from shopman.shop.projections.order_queue import (
    build_operator_order,
    build_order_card,
    build_order_queue,
)
from shopman.shop.services.cancellation import cancel

NOTIFICATION_SEND = "notification.send"

logger = logging.getLogger(__name__)


def _staff_required(request):
    """Check staff auth; return redirect response or None."""
    if not request.user.is_staff:
        return redirect(f"/admin/login/?next={request.path}")
    return None


class OperatorOrdersView(View):
    """Main operator dashboard page."""

    def get(self, request: HttpRequest) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        filter_status = request.GET.get("filter", "all")
        queue = build_order_queue(filter_status=filter_status)

        from shopman.shop.models import Shop
        shop = Shop.load()

        return render(request, "pedidos/index.html", {
            "queue": queue,
            "orders": queue.orders,
            "counts": queue.counts,
            "filter": queue.active_filter,
            "shop": shop,
        })


class OrderListPartialView(View):
    """HTMX partial: returns order grid for polling updates."""

    def get(self, request: HttpRequest) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        filter_status = request.GET.get("filter", "all")
        queue = build_order_queue(filter_status=filter_status)

        return render(request, "pedidos/partials/order_list.html", {
            "orders": queue.orders,
            "counts": queue.counts,
            "filter": queue.active_filter,
        })


class OrderDetailPartialView(View):
    """HTMX partial: expanded detail for a single order card."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        order = get_object_or_404(Order, ref=ref)
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
        denied = _staff_required(request)
        if denied:
            return denied

        order = get_object_or_404(Order, ref=ref)
        if order.status != "new":
            return HttpResponse("Pedido não está aguardando confirmação", status=422)

        from shopman.shop.lifecycle import ensure_confirmable

        try:
            ensure_confirmable(order)
        except Exception as exc:
            logger.exception("ensure_confirmable failed for order %s", ref)
            return HttpResponse(str(exc), status=422)

        order.transition_status("confirmed", actor=f"operator:{request.user.username}")

        card = build_order_card(order)
        return render(request, "pedidos/partials/card.html", {"o": card})


class OrderRejectView(View):
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
        return HttpResponse("")


class OrderAdvanceView(View):
    """POST /pedidos/<ref>/advance/ — advance to next status."""

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        order = get_object_or_404(Order, ref=ref)

        from shopman.shop.projections.order_queue import _next_status
        next_status = _next_status(order)
        if not next_status:
            return HttpResponse("", status=422)

        order.transition_status(next_status, actor=f"operator:{request.user.username}")

        card = build_order_card(order)
        return render(request, "pedidos/partials/card.html", {"o": card})


class OrderNotesView(View):
    """POST /pedidos/<ref>/notes/ — save internal notes."""

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        order = get_object_or_404(Order, ref=ref)
        order.data["internal_notes"] = request.POST.get("notes", "")
        order.save(update_fields=["data", "updated_at"])

        return HttpResponse('<span class="ped-notes-saved">Salvo</span>')


class OrderMarkPaidView(View):
    """POST /pedidos/<ref>/mark-paid/ — operador confirma recebimento manual (dinheiro/counter)."""

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        denied = _staff_required(request)
        if denied:
            return denied

        order = get_object_or_404(Order, ref=ref)

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
        return render(request, "pedidos/partials/card.html", {"o": card})
