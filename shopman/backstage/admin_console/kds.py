"""Admin/Unfold KDS operational console."""

from __future__ import annotations

from django.contrib import admin, messages
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView
from unfold.views import UnfoldModelAdminViewMixin

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.backstage.projections.kds import (
    KDSExpeditionCardProjection,
    KDSTicketProjection,
    build_kds_board,
    build_kds_index,
)
from shopman.backstage.services import kds as kds_service
from shopman.backstage.services.exceptions import KDSError

INDEX_TEMPLATE = "admin_console/kds/index.html"
DISPLAY_TEMPLATE = "admin_console/kds/display.html"
PARTIAL_TEMPLATE = "admin_console/kds/partials/tickets.html"
STATION_CELL_TEMPLATE = "admin_console/kds/cells/station.html"
TICKET_ACTIONS_CELL_TEMPLATE = "admin_console/kds/cells/ticket_actions.html"
ITEM_ACTION_CELL_TEMPLATE = "admin_console/kds/cells/item_action.html"
EXPEDITION_ACTIONS_CELL_TEMPLATE = "admin_console/kds/cells/expedition_actions.html"
PERM = "backstage.operate_kds"


class KDSConsoleIndexView(UnfoldModelAdminViewMixin, TemplateView):
    """KDS station selector inside the Admin shell."""

    template_name = INDEX_TEMPLATE
    title = "KDS"
    permission_required: tuple[str, ...] = ()

    def has_permission(self) -> bool:
        return _is_staff(self.request.user)

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not _is_staff(request.user):
            return HttpResponseForbidden("Voce precisa ser staff para acessar o KDS.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        instances = build_kds_index()
        context.update({
            "kds_station_table": _station_table(self.request, instances),
            "kds_is_readonly": not _can_operate_kds(self.request.user),
        })
        return context


class KDSConsoleDisplayView(UnfoldModelAdminViewMixin, TemplateView):
    """KDS station display inside the Admin shell."""

    template_name = DISPLAY_TEMPLATE
    title = "KDS"
    permission_required: tuple[str, ...] = ()

    def has_permission(self) -> bool:
        return _is_staff(self.request.user)

    def dispatch(self, request: HttpRequest, ref: str, *args, **kwargs) -> HttpResponse:
        if not _is_staff(request.user):
            return HttpResponseForbidden("Voce precisa ser staff para acessar o KDS.")
        self.instance = get_object_or_404(KDSInstance, ref=ref, is_active=True)
        return super().dispatch(request, ref, *args, **kwargs)

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        context.update(build_kds_console_context(self.request, self.instance.ref))
        return context


class KDSConsoleTicketListPartialView(UnfoldModelAdminViewMixin, TemplateView):
    """HTMX/SSE refresh target for a KDS station."""

    template_name = PARTIAL_TEMPLATE
    title = "KDS"
    permission_required: tuple[str, ...] = ()

    def has_permission(self) -> bool:
        return _is_staff(self.request.user)

    def dispatch(self, request: HttpRequest, ref: str, *args, **kwargs) -> HttpResponse:
        if not _is_staff(request.user):
            return HttpResponseForbidden("Voce precisa ser staff para acessar o KDS.")
        self.instance = get_object_or_404(KDSInstance, ref=ref, is_active=True)
        return super().dispatch(request, ref, *args, **kwargs)

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        context.update(build_kds_console_context(self.request, self.instance.ref))
        return context


def _kds_model_admin():
    try:
        return admin.site._registry[KDSInstance]
    except KeyError as exc:
        raise ImproperlyConfigured("KDSInstance must be registered in admin.site for the KDS Admin page.") from exc


def kds_console_index_as_view():
    return KDSConsoleIndexView.as_view(model_admin=_kds_model_admin())


def kds_console_index_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    return kds_console_index_as_view()(request, *args, **kwargs)


def kds_console_display_as_view():
    return KDSConsoleDisplayView.as_view(model_admin=_kds_model_admin())


def kds_console_display_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    return kds_console_display_as_view()(request, *args, **kwargs)


def kds_console_ticket_list_as_view():
    return KDSConsoleTicketListPartialView.as_view(model_admin=_kds_model_admin())


def kds_console_ticket_list_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    return kds_console_ticket_list_as_view()(request, *args, **kwargs)


@require_POST
def kds_ticket_check_view(request: HttpRequest, pk: int) -> HttpResponse:
    if not _can_operate_kds(request.user):
        return HttpResponseForbidden("Voce nao tem permissao para operar o KDS.")
    index = int(request.POST.get("index", 0))
    try:
        ticket = kds_service.check_ticket_item(
            ticket_pk=pk,
            index=index,
            actor=f"kds:{request.user.username}",
        )
    except KDSError as exc:
        return HttpResponse(str(exc), status=404)
    return _kds_station_redirect(ticket.kds_instance.ref)


@require_POST
def kds_ticket_done_view(request: HttpRequest, pk: int) -> HttpResponse:
    if not _can_operate_kds(request.user):
        return HttpResponseForbidden("Voce nao tem permissao para operar o KDS.")
    try:
        ticket = kds_service.mark_ticket_done(ticket_pk=pk, actor=f"kds:{request.user.username}")
    except KDSError as exc:
        return HttpResponse(str(exc), status=404)
    return _kds_station_redirect(ticket.kds_instance.ref)


@require_POST
def kds_expedition_action_view(request: HttpRequest, pk: int) -> HttpResponse:
    if not _can_operate_kds(request.user):
        return HttpResponseForbidden("Voce nao tem permissao para operar o KDS.")
    action = request.POST.get("action", "")
    try:
        kds_service.expedition_action(
            order_id=pk,
            action=action,
            actor=f"kds:{request.user.username}",
        )
    except KDSError as exc:
        return HttpResponse(str(exc), status=422)
    messages.success(request, "Expedicao atualizada.")
    return HttpResponseRedirect(reverse("admin_console_kds"))


def build_kds_console_context(request: HttpRequest, ref: str) -> dict:
    board = build_kds_board(ref)
    is_readonly = not _can_operate_kds(request.user)
    return {
        "kds_instance": KDSInstance.objects.get(ref=ref, is_active=True),
        "kds_board": board,
        "kds_ticket_table": _ticket_table(request, board, is_readonly=is_readonly),
        "kds_tickets_url": reverse("admin_console_kds_tickets", args=[ref]),
        "kds_index_url": reverse("admin_console_kds"),
        "kds_is_readonly": is_readonly,
    }


def _station_table(request: HttpRequest, instances) -> dict:
    return {
        "headers": ["Estacao", "Tipo", "Pendentes"],
        "rows": [
            [
                _station_cell(request, entry),
                entry.type_display,
                entry.pending_count,
            ]
            for entry in instances
        ],
    }


def _ticket_table(request: HttpRequest, board, *, is_readonly: bool) -> dict:
    if board.is_expedition:
        return {
            "collapsible": True,
            "headers": ["Pedido", "Cliente", "Entrega", "Unidades", "Linhas", "Total", "Acao"],
            "rows": [_expedition_row(request, item, is_readonly=is_readonly) for item in board.tickets],
        }
    return {
        "collapsible": True,
        "headers": ["Pedido", "Cliente", "Tempo", "Itens", "Estado", "Acao"],
        "rows": [_ticket_row(request, item, is_readonly=is_readonly) for item in board.tickets],
    }


def _ticket_row(request: HttpRequest, ticket: KDSTicketProjection, *, is_readonly: bool) -> dict:
    return {
        "cols": [
            f"#{ticket.order_ref}",
            ticket.customer_name or "-",
            _elapsed_label(ticket.elapsed_seconds, ticket.target_seconds),
            _items_summary(ticket),
            "Conferido" if ticket.all_checked else "Pendente",
            _ticket_actions_cell(request, ticket, is_readonly=is_readonly),
        ],
        "table": _ticket_detail_table(request, ticket, is_readonly=is_readonly),
    }


def _expedition_row(request: HttpRequest, item: KDSExpeditionCardProjection, *, is_readonly: bool) -> dict:
    return {
        "cols": [
            f"#{item.ref}",
            item.customer_name or "-",
            item.fulfillment_label,
            f"{item.units_count} un.",
            item.line_count,
            item.total_display,
            _expedition_actions_cell(request, item, is_readonly=is_readonly),
        ],
        "table": {
            "headers": ["Campo", "Valor"],
            "rows": [
                ["Pedido", item.ref],
                ["Entrega", item.fulfillment_label],
                ["Unidades", f"{item.units_count} un."],
                ["Linhas", item.line_count],
            ],
        },
    }


def _ticket_detail_table(request: HttpRequest, ticket: KDSTicketProjection, *, is_readonly: bool) -> dict:
    return {
        "headers": ["SKU", "Item", "Qtd", "Notas", "Estoque", "Conferencia"],
        "rows": [
            [
                item.sku,
                item.name,
                item.qty,
                item.notes or "-",
                item.stock_warning or "-",
                "Conferido" if is_readonly else _item_action_cell(request, ticket, index, checked=item.checked),
            ]
            for index, item in enumerate(ticket.items)
        ],
    }


def _station_cell(request: HttpRequest, entry):
    return mark_safe(
        render_to_string(
            STATION_CELL_TEMPLATE,
            {
                "entry": entry,
                "display_url": reverse("admin_console_kds_display", args=[entry.ref]),
                "runtime_url": reverse("backstage:kds_station_runtime", args=[entry.ref]),
            },
            request=request,
        )
    )


def _ticket_actions_cell(request: HttpRequest, ticket: KDSTicketProjection, *, is_readonly: bool):
    return mark_safe(
        render_to_string(
            TICKET_ACTIONS_CELL_TEMPLATE,
            {
                "ticket": ticket,
                "is_readonly": is_readonly,
                "done_url": reverse("admin_console_kds_ticket_done", args=[ticket.pk]),
            },
            request=request,
        )
    )


def _item_action_cell(request: HttpRequest, ticket: KDSTicketProjection, index: int, *, checked: bool):
    return mark_safe(
        render_to_string(
            ITEM_ACTION_CELL_TEMPLATE,
            {
                "ticket": ticket,
                "index": index,
                "checked": checked,
                "check_url": reverse("admin_console_kds_ticket_check", args=[ticket.pk]),
            },
            request=request,
        )
    )


def _expedition_actions_cell(request: HttpRequest, item: KDSExpeditionCardProjection, *, is_readonly: bool):
    return mark_safe(
        render_to_string(
            EXPEDITION_ACTIONS_CELL_TEMPLATE,
            {
                "item": item,
                "is_readonly": is_readonly,
                "action_url": reverse("admin_console_kds_expedition_action", args=[item.pk]),
            },
            request=request,
        )
    )


def _kds_station_redirect(ref: str) -> HttpResponseRedirect:
    return HttpResponseRedirect(reverse("admin_console_kds_display", args=[ref]))


def _is_staff(user) -> bool:
    return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))


def _can_operate_kds(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or user.has_perm(PERM))


def _items_summary(ticket: KDSTicketProjection) -> str:
    total = sum(item.qty for item in ticket.items)
    lines = len(ticket.items)
    line_label = "linha" if lines == 1 else "linhas"
    return f"{total} un. - {lines} {line_label}"


def _elapsed_label(seconds: int, target_seconds: int) -> str:
    minutes, remainder = divmod(max(seconds, 0), 60)
    target_minutes = max(target_seconds // 60, 1)
    return f"{minutes}:{remainder:02d} / {target_minutes}min"
