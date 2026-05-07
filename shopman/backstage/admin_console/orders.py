"""Admin/Unfold operational order console."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ImproperlyConfigured
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView
from shopman.orderman.models import Order
from unfold.views import UnfoldModelAdminViewMixin
from unfold.widgets import UnfoldAdminTextareaWidget

from shopman.backstage.projections.order_queue import (
    OrderCardProjection,
    build_operator_order,
    build_order_card,
    build_two_zone_queue,
)
from shopman.backstage.services import alerts as alert_service
from shopman.backstage.services import orders as order_service
from shopman.backstage.services.exceptions import OrderError

TEMPLATE = "admin_console/orders/index.html"
PARTIAL_TEMPLATE = "admin_console/orders/partials/sections.html"
DETAIL_TEMPLATE = "admin_console/orders/detail.html"
REJECT_TEMPLATE = "admin_console/orders/reject.html"
ACTION_CELL_TEMPLATE = "admin_console/orders/cells/actions.html"
ORDER_REF_CELL_TEMPLATE = "admin_console/orders/cells/order_ref.html"
PERM = "shop.manage_orders"
logger = logging.getLogger(__name__)


class OrderRejectForm(forms.Form):
    reason = forms.CharField(
        label="Motivo da rejeicao",
        widget=UnfoldAdminTextareaWidget(attrs={"class": "max-w-none", "rows": 4}),
    )


class OrderNotesForm(forms.Form):
    notes = forms.CharField(
        label="Notas internas",
        required=False,
        widget=UnfoldAdminTextareaWidget(attrs={"class": "max-w-none", "rows": 5}),
    )


@dataclass(frozen=True)
class OrderSection:
    title: str
    subtitle: str
    table: dict


class OrdersConsoleView(UnfoldModelAdminViewMixin, TemplateView):
    """Live order queue rendered through the official Unfold custom-page mixin."""

    template_name = TEMPLATE
    title = "Pedidos"
    permission_required: tuple[str, ...] = ()

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not _can_manage_orders(request.user):
            return HttpResponseForbidden("Voce nao tem permissao para acessar pedidos.")
        return super().dispatch(request, *args, **kwargs)

    def has_permission(self) -> bool:
        return _can_manage_orders(self.request.user)

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        context.update(build_orders_console_context(self.request))
        return context


class OrdersConsoleListPartialView(UnfoldModelAdminViewMixin, TemplateView):
    """HTMX/SSE refresh target for the Admin order queue tables."""

    template_name = PARTIAL_TEMPLATE
    title = "Pedidos"
    permission_required: tuple[str, ...] = ()

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not _can_manage_orders(request.user):
            return HttpResponseForbidden("Voce nao tem permissao para esta acao.")
        return super().dispatch(request, *args, **kwargs)

    def has_permission(self) -> bool:
        return _can_manage_orders(self.request.user)

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        context.update(build_orders_console_context(self.request))
        return context


class OrderDetailView(UnfoldModelAdminViewMixin, TemplateView):
    """Single order operational detail inside the Admin shell."""

    template_name = DETAIL_TEMPLATE
    title = "Pedido"
    permission_required: tuple[str, ...] = ()

    def dispatch(self, request: HttpRequest, ref: str, *args, **kwargs) -> HttpResponse:
        if not _can_manage_orders(request.user):
            return HttpResponseForbidden("Voce nao tem permissao para acessar pedidos.")
        self.order = _order_or_404(ref)
        return super().dispatch(request, ref, *args, **kwargs)

    def has_permission(self) -> bool:
        return _can_manage_orders(self.request.user)

    def post(self, request: HttpRequest, ref: str, *args, **kwargs) -> HttpResponse:
        form = OrderNotesForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        order_service.save_internal_notes(self.order, notes=form.cleaned_data["notes"])
        messages.success(request, f"Notas do pedido #{self.order.ref} salvas.")
        return HttpResponseRedirect(reverse("admin_console_order_detail", args=[self.order.ref]))

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        detail = build_operator_order(self.order)
        card = build_order_card(self.order)
        form = kwargs.get("form") or OrderNotesForm(initial={"notes": detail.internal_notes})
        context.update({
            "order_detail": detail,
            "order_card": card,
            "order_notes_form": form,
            "order_notes_fields": (form["notes"],),
            "order_admin_url": reverse("admin:orderman_order_change", args=[self.order.pk]),
            "order_console_url": reverse("admin_console_orders"),
            "order_reject_url": reverse("admin_console_order_reject", args=[self.order.ref]),
            "order_actions_cell": _actions_cell(self.request, card, include_detail=False),
            "order_items_table": _items_table(detail),
            "order_timeline_table": _timeline_table(detail),
        })
        return context


class OrderRejectView(UnfoldModelAdminViewMixin, TemplateView):
    """Reject an order with a required reason through an Admin/Unfold form."""

    template_name = REJECT_TEMPLATE
    title = "Rejeitar pedido"
    permission_required: tuple[str, ...] = ()

    def dispatch(self, request: HttpRequest, ref: str, *args, **kwargs) -> HttpResponse:
        if not _can_manage_orders(request.user):
            return HttpResponseForbidden("Voce nao tem permissao para rejeitar pedidos.")
        self.order = _order_or_404(ref)
        return super().dispatch(request, ref, *args, **kwargs)

    def has_permission(self) -> bool:
        return _can_manage_orders(self.request.user)

    def post(self, request: HttpRequest, ref: str, *args, **kwargs) -> HttpResponse:
        form = OrderRejectForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        try:
            order_service.reject_order(
                self.order,
                reason=form.cleaned_data["reason"],
                actor=f"operator:{request.user.username}",
                rejected_by=request.user.username,
            )
        except OrderError as exc:
            messages.error(request, str(exc))
            return self.render_to_response(self.get_context_data(form=form))
        messages.success(request, f"Pedido #{self.order.ref} rejeitado.")
        return HttpResponseRedirect(reverse("admin_console_orders"))

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        form = kwargs.get("form") or OrderRejectForm()
        context.update({
            "order": self.order,
            "order_reject_form": form,
            "order_reject_fields": (form["reason"],),
            "order_console_url": reverse("admin_console_orders"),
            "order_detail_url": reverse("admin_console_order_detail", args=[self.order.ref]),
        })
        return context


def _order_model_admin():
    try:
        return admin.site._registry[Order]
    except KeyError as exc:
        raise ImproperlyConfigured("Order must be registered in admin.site for the Orders Admin page.") from exc


def orders_console_as_view():
    return OrdersConsoleView.as_view(model_admin=_order_model_admin())


def orders_console_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    return orders_console_as_view()(request, *args, **kwargs)


def orders_console_list_as_view():
    return OrdersConsoleListPartialView.as_view(model_admin=_order_model_admin())


def orders_console_list_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    return orders_console_list_as_view()(request, *args, **kwargs)


def order_detail_as_view():
    return OrderDetailView.as_view(model_admin=_order_model_admin())


def order_detail_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    return order_detail_as_view()(request, *args, **kwargs)


def order_reject_as_view():
    return OrderRejectView.as_view(model_admin=_order_model_admin())


def order_reject_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    return order_reject_as_view()(request, *args, **kwargs)


@require_POST
def order_confirm_view(request: HttpRequest, ref: str) -> HttpResponse:
    if not _can_manage_orders(request.user):
        return HttpResponseForbidden("Voce nao tem permissao para esta acao.")
    order = _order_or_404(ref)
    try:
        order_service.confirm_order(order, actor=f"operator:{request.user.username}")
    except Exception as exc:
        logger.exception("admin_console_order_confirm_failed ref=%s", ref)
        return HttpResponse(str(exc), status=422)
    messages.success(request, f"Pedido #{order.ref} confirmado.")
    return _orders_redirect()


@require_POST
def order_advance_view(request: HttpRequest, ref: str) -> HttpResponse:
    if not _can_manage_orders(request.user):
        return HttpResponseForbidden("Voce nao tem permissao para esta acao.")
    order = _order_or_404(ref)
    try:
        order_service.advance_order(order, actor=f"operator:{request.user.username}")
    except OrderError as exc:
        return HttpResponse(str(exc), status=422)
    updated = build_order_card(order)
    messages.success(request, f"Pedido #{order.ref}: {updated.status_label}.")
    return _orders_redirect()


def build_orders_console_context(request: HttpRequest) -> dict:
    queue = build_two_zone_queue()
    return {
        "order_flow_tabs": _order_flow_tabs(active="orders"),
        "order_status_tracker": _status_tracker(queue),
        "order_sections": _order_sections(request, queue),
        "orders_list_url": reverse("admin_console_orders_list"),
        "orders_total_count": queue.total_count,
        "orders_last_updated": timezone.localtime(timezone.now()).strftime("%H:%M"),
        "order_alerts": alert_service.list_active_alerts(limit=10),
    }


def _order_sections(request: HttpRequest, queue) -> tuple[OrderSection, ...]:
    return (
        OrderSection(
            title="Entrada",
            subtitle="Pedidos novos para confirmar ou rejeitar.",
            table=_order_table(request, queue.entrada),
        ),
        OrderSection(
            title="Preparo",
            subtitle="Pedidos confirmados ou em preparo.",
            table=_order_table(request, queue.preparo),
        ),
        OrderSection(
            title="Saida",
            subtitle="Retirada, coleta e entrega.",
            table=_order_table(
                request,
                (*queue.saida_retirada, *queue.saida_delivery, *queue.saida_delivery_transit),
            ),
        ),
    )


def _order_table(request: HttpRequest, cards: tuple[OrderCardProjection, ...]) -> dict:
    return {
        "collapsible": True,
        "headers": ["Pedido", "Cliente", "Tempo", "Itens", "Entrega", "Total", "Pagamento", "Acao"],
        "rows": [_order_row(request, card) for card in cards],
    }


def _order_row(request: HttpRequest, card: OrderCardProjection) -> dict:
    return {
        "cols": [
            _order_ref_cell(request, card),
            card.customer_name or "-",
            _elapsed_label(card.elapsed_seconds),
            card.items_summary,
            card.fulfillment_label,
            card.total_display,
            card.payment_method_label or "-",
            _actions_cell(request, card),
        ],
        "table": _order_detail_table(card),
    }


def _order_detail_table(card: OrderCardProjection) -> dict:
    rows = [
        ["Status", card.status_label, card.channel_ref or "-", card.next_action_label or "-"],
        ["Pagamento", card.payment_method_label or "-", card.payment_status or "-", "Pendente" if card.payment_pending else "Liberado"],
    ]
    for wo in card.awaiting_work_orders:
        rows.append(["Producao", wo.ref, wo.status_label, f"{wo.output_sku} - {wo.progress_pct}%"])
    return {
        "headers": ["Tipo", "Referencia", "Estado", "Detalhe"],
        "rows": rows,
    }


def _items_table(detail) -> dict:
    return {
        "headers": ["SKU", "Item", "Qtd", "Unitario", "Total"],
        "rows": [
            [item.sku, item.name, item.qty, item.unit_price_display, item.total_display]
            for item in detail.items
        ],
    }


def _timeline_table(detail) -> dict:
    return {
        "headers": ["Quando", "Evento", "Ator", "Detalhe"],
        "rows": [
            [item.timestamp_display, item.label, item.actor or "-", item.detail or "-"]
            for item in detail.timeline
        ],
    }


def _order_flow_tabs(*, active: str) -> tuple[dict, ...]:
    return (
        {
            "title": "Ativos",
            "link": reverse("admin_console_orders"),
            "active": active == "orders",
            "has_permission": True,
        },
        {
            "title": "Historico",
            "link": reverse("admin:orderman_order_changelist"),
            "active": active == "history",
            "has_permission": True,
        },
    )


def _status_tracker(queue) -> tuple[dict, ...]:
    colors = {
        "new": "bg-amber-500 dark:bg-amber-600",
        "confirmed": "bg-blue-500 dark:bg-blue-600",
        "preparing": "bg-orange-500 dark:bg-orange-600",
        "ready": "bg-green-600 dark:bg-green-700",
        "dispatched": "bg-primary-600 dark:bg-primary-500",
        "delivered": "bg-base-500 dark:bg-base-400",
    }
    cards = (
        *queue.entrada,
        *queue.preparo,
        *queue.saida_retirada,
        *queue.saida_delivery,
        *queue.saida_delivery_transit,
    )
    return tuple(
        {
            "color": colors.get(card.status, "bg-base-300 dark:bg-base-500"),
            "tooltip": f"{card.ref} - {card.status_label} - {card.customer_name or 'sem cliente'}",
            "href": reverse("admin_console_order_detail", args=[card.ref]),
        }
        for card in cards[:80]
    )


def _order_ref_cell(request: HttpRequest, card: OrderCardProjection):
    return mark_safe(
        render_to_string(
            ORDER_REF_CELL_TEMPLATE,
            {"card": card, "detail_url": reverse("admin_console_order_detail", args=[card.ref])},
            request=request,
        )
    )


def _actions_cell(request: HttpRequest, card: OrderCardProjection, *, include_detail: bool = True):
    return mark_safe(
        render_to_string(
            ACTION_CELL_TEMPLATE,
            {
                "card": card,
                "include_detail": include_detail,
                "detail_url": reverse("admin_console_order_detail", args=[card.ref]),
                "confirm_url": reverse("admin_console_order_confirm", args=[card.ref]),
                "advance_url": reverse("admin_console_order_advance", args=[card.ref]),
                "reject_url": reverse("admin_console_order_reject", args=[card.ref]),
            },
            request=request,
        )
    )


def _order_or_404(ref: str) -> Order:
    order = order_service.find_order(ref)
    if order is None:
        raise Http404("Pedido nao encontrado.")
    return order


def _orders_redirect() -> HttpResponseRedirect:
    return HttpResponseRedirect(reverse("admin_console_orders"))


def _can_manage_orders(user) -> bool:
    return bool(
        getattr(user, "is_superuser", False)
        or user.has_perm(PERM)
    )


def _elapsed_label(seconds: int) -> str:
    minutes, remainder = divmod(max(seconds, 0), 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes}min"
    return f"{minutes}:{remainder:02d}"
