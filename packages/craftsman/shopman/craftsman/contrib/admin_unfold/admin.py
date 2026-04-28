"""
Craftsman Admin with Unfold theme (vNext).

Registers Unfold-styled admin classes for vNext models:
- Recipe + RecipeItem inline
- WorkOrder + WorkOrderItem + WorkOrderEvent inlines

To use, add 'shopman.craftsman.contrib.admin_unfold' to INSTALLED_APPS after 'crafting'.
"""

import logging
from importlib import import_module

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from shopman.craftsman.models import (
    Recipe,
    RecipeItem,
    WorkOrder,
    WorkOrderEvent,
    WorkOrderItem,
)
from shopman.utils.contrib.admin_unfold.badges import unfold_badge, unfold_badge_numeric
from shopman.utils.contrib.admin_unfold.base import (
    BaseModelAdmin,
    BaseStackedInline,
    BaseTabularInline,
)
from shopman.utils.formatting import format_quantity
from unfold.contrib.filters.admin.datetime_filters import RangeDateFilter
from unfold.contrib.filters.admin.dropdown_filters import ChoicesDropdownFilter
from unfold.decorators import action, display
from unfold.enums import ActionVariant
from unfold.sections import TableSection

logger = logging.getLogger(__name__)


# =============================================================================
# RECIPE ADMIN
# =============================================================================


class RecipeItemInline(BaseStackedInline):
    """Inline for recipe items (insumos)."""

    model = RecipeItem
    extra = 0
    tab = True

    fieldsets = (
        (
            None,
            {
                "fields": ("input_sku", "quantity", "unit"),
            },
        ),
        (
            _("Opções"),
            {
                "classes": ["collapse"],
                "fields": ("sort_order", "is_optional", "meta"),
            },
        ),
    )


@admin.register(Recipe)
class RecipeAdmin(BaseModelAdmin):
    """Admin interface for Recipe."""

    compressed_fields = True
    warn_unsaved_form = True

    list_display = [
        "ref",
        "name",
        "output_sku",
        "batch_size",
        "is_active",
    ]
    list_filter = ["is_active"]
    search_fields = ["ref", "name", "output_sku"]
    ordering = ["name"]
    prepopulated_fields = {"ref": ("name",)}

    inlines = [RecipeItemInline]

    fieldsets = (
        (
            _("Identificação"),
            {"fields": ("ref", "name", "is_active")},
        ),
        (
            _("Produção"),
            {
                "classes": ["tab"],
                "fields": ("output_sku", "batch_size"),
            },
        ),
        (
            _("Etapas"),
            {
                "classes": ["tab"],
                "fields": ("steps",),
            },
        ),
        (
            _("Avançado"),
            {
                "classes": ["tab", "collapse"],
                "fields": ("meta",),
            },
        ),
    )


# =============================================================================
# WORK ORDER ADMIN
# =============================================================================


class WorkOrderItemInline(BaseTabularInline):
    """Inline for work order items (ledger entries). Read-only."""

    model = WorkOrderItem
    extra = 0
    tab = True
    fields = ["kind", "item_ref", "quantity", "unit", "recorded_at", "recorded_by"]
    readonly_fields = ["kind", "item_ref", "quantity", "unit", "recorded_at", "recorded_by"]

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class WorkOrderEventInline(BaseTabularInline):
    """Inline for work order events (audit trail). Read-only."""

    model = WorkOrderEvent
    extra = 0
    tab = True
    fields = ["seq", "kind", "payload", "actor", "created_at"]
    readonly_fields = ["seq", "kind", "payload", "actor", "created_at"]

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


_KIND_BADGE_COLORS = {
    WorkOrderItem.Kind.REQUIREMENT: "blue",
    WorkOrderItem.Kind.CONSUMPTION: "yellow",
    WorkOrderItem.Kind.OUTPUT: "green",
    WorkOrderItem.Kind.WASTE: "red",
}


class WorkOrderItemSection(TableSection):
    related_name = "items"
    fields = ["kind", "item_ref", "quantity", "unit"]
    verbose_name = _("Itens da Ordem de Produção")

    def kind(self, obj):
        color = _KIND_BADGE_COLORS.get(obj.kind, "base")
        return unfold_badge(obj.get_kind_display(), color)
    kind.short_description = _("Tipo")


@admin.register(WorkOrder)
class WorkOrderAdmin(BaseModelAdmin):
    """
    Admin de Execução (vNext).

    4 estados: planned, started, finished, void.
    Campos editáveis: quantity (via adjust enquanto planned), target_date.
    """

    compressed_fields = True
    warn_unsaved_form = True
    change_list_template = "craftsman/admin/workorder_change_list.html"

    list_display = [
        "ref",
        "product_display",
        "date_display",
        "preorder_indicator",
        "quantity",
        "produced_display",
        "loss_display",
        "commitments_display",
        "status_badge",
        "operation_link_display",
    ]

    list_filter = [
        "status",
        ("recipe", ChoicesDropdownFilter),
        ("target_date", RangeDateFilter),
        "position_ref",
        "operator_ref",
    ]
    list_filter_submit = True
    search_fields = ["ref", "recipe__name", "output_sku"]
    date_hierarchy = "target_date"
    ordering = ["-created_at"]
    autocomplete_fields = ["recipe"]

    inlines = [WorkOrderItemInline, WorkOrderEventInline]
    actions_row = ["close_wo_row", "void_wo_row"]
    actions_detail = ["close_wo_row", "void_wo_row"]
    actions = ["finish_selected_work_orders", "void_selected_work_orders"]
    list_sections = [WorkOrderItemSection]

    fieldsets = (
        (
            _("Identificação"),
            {"fields": ("ref", "recipe", "output_sku", "status")},
        ),
        (
            _("Quantidades"),
            {
                "classes": ["tab"],
                "fields": ("quantity", "finished"),
            },
        ),
        (
            _("Agendamento"),
            {
                "classes": ["tab"],
                "fields": ("target_date", "started_at", "finished_at"),
            },
        ),
        (
            _("Referências"),
            {
                "classes": ["tab"],
                "fields": ("source_ref", "position_ref", "operator_ref"),
            },
        ),
        (
            _("Avançado"),
            {
                "classes": ["tab", "collapse"],
                "fields": ("rev", "meta"),
            },
        ),
    )

    readonly_fields = [
        "ref",
        "output_sku",
        "status",
        "finished",
        "rev",
        "started_at",
        "finished_at",
    ]

    @display(description=_("Produto"))
    def product_display(self, obj):
        """Display output product ref."""
        return obj.output_sku or "-"

    @display(description=_("Data"))
    def date_display(self, obj):
        """Display date in DD/MM/YY format."""
        if obj.target_date:
            return obj.target_date.strftime("%d/%m/%y")
        return "-"

    @display(description=_("Tipo"))
    def preorder_indicator(self, obj):
        """Show badge if WorkOrder is scheduled for a future date (preorder/programado)."""
        if obj.target_date and obj.target_date > timezone.localdate():
            return unfold_badge(_("Programado"), "purple")
        return ""

    @display(description=_("Produzido"))
    def produced_display(self, obj):
        """Display finished quantity."""
        if obj.finished is not None:
            return unfold_badge_numeric(format_quantity(obj.finished), "green")
        return "-"

    @display(description=_("Perda"))
    def loss_display(self, obj):
        """Display loss quantity and percentage."""
        loss = obj.loss
        if loss is None:
            return "-"
        if loss == 0:
            return unfold_badge_numeric("0", "green")

        yield_rate = obj.yield_rate
        loss_pct = (1 - float(yield_rate)) * 100 if yield_rate else 0
        loss_formatted = format_quantity(loss)

        if loss_pct > 10:
            return unfold_badge_numeric(f"{loss_formatted} ({loss_pct:.1f}%)", "red")
        elif loss_pct > 5:
            return unfold_badge_numeric(f"{loss_formatted} ({loss_pct:.1f}%)", "yellow")
        else:
            return unfold_badge_numeric(loss_formatted, "base")

    @display(description=_("Compromisso"))
    def commitments_display(self, obj):
        refs = _committed_order_refs(obj)
        if not refs:
            return "-"
        qty = _committed_qty_for_work_order(obj)
        return unfold_badge_numeric(
            _("%(qty)s un. / %(orders)d ped.") % {"qty": format_quantity(qty), "orders": len(refs)},
            "blue",
        )

    @display(description=_("Operação"))
    def operation_link_display(self, obj):
        if obj.target_date:
            board_url = f'{reverse("backstage:production")}?date={obj.target_date.isoformat()}'
        else:
            board_url = reverse("backstage:production")
        if _committed_order_refs(obj):
            commitments_url = reverse("backstage:production_work_order_commitments", args=[obj.ref])
            return format_html(
                '<a class="font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400" href="{}">Mapa</a>'
                '<span class="text-base-300 px-1">·</span>'
                '<a class="font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400" href="{}">Pedidos</a>',
                board_url,
                commitments_url,
            )
        return format_html(
            '<a class="font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400" href="{}">Mapa</a>',
            board_url,
        )

    @display(description=_("Status"))
    def status_badge(self, obj):
        """Display colored status badge."""
        colors = {
            WorkOrder.Status.PLANNED: "blue",
            WorkOrder.Status.STARTED: "yellow",
            WorkOrder.Status.FINISHED: "green",
            WorkOrder.Status.VOID: "red",
        }
        color = colors.get(obj.status, "base")
        return unfold_badge(obj.get_status_display(), color)

    def get_readonly_fields(self, request, obj=None):
        """Make ref readonly only for existing objects."""
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and "ref" not in readonly:
            readonly.append("ref")
        return readonly

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("recipe")
            .prefetch_related("items", "events")
        )

    def changelist_view(self, request, extra_context=None):
        """Auto-redirect to today if no date filter."""
        date_year = request.GET.get("target_date__year")
        date_month = request.GET.get("target_date__month")
        date_day = request.GET.get("target_date__day")

        has_any_date_param = bool(date_year or date_month or date_day)

        has_admin_nav = any(
            [
                "_changelist_filters" in request.GET,
                "p" in request.GET,
                "o" in request.GET,
                "q" in request.GET,
                "status__exact" in request.GET,
                "recipe__id__exact" in request.GET,
            ]
        )

        if not has_any_date_param and not has_admin_nav:
            today = timezone.localdate()
            changelist_url = reverse("admin:craftsman_workorder_changelist")
            return redirect(
                f"{changelist_url}?"
                f"target_date__year={today.year}&"
                f"target_date__month={today.month}&"
                f"target_date__day={today.day}"
            )

        return super().changelist_view(request, extra_context)

    @action(
        description=_("Finalizar ✓"),
        url_path="finish-wo",
        icon="check_circle",
        variant=ActionVariant.SUCCESS,
    )
    def close_wo_row(self, request, object_id):
        wo = self.get_object(request, object_id)
        if wo is None:
            messages.error(request, _("Ordem não encontrada."))
            return HttpResponseRedirect(reverse("admin:craftsman_workorder_changelist"))

        if wo.status not in (WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED):
            messages.warning(request, _("Apenas ordens planned/started podem ser finalizadas."))
            return HttpResponseRedirect(reverse("admin:craftsman_workorder_changelist"))

        actor = getattr(request.user, "username", None) or "admin"
        try:
            _finish_work_order_from_admin(wo, actor=actor)
            messages.success(
                request,
                _("Ordem %(code)s finalizada (resultado: %(qty)s).") % {
                    "code": wo.ref,
                    "qty": format_quantity(wo.started_qty or wo.quantity),
                },
            )
        except Exception as exc:
            messages.error(request, str(exc))

        return HttpResponseRedirect(reverse("admin:craftsman_workorder_changelist"))

    @action(
        description=_("Cancelar ✕"),
        url_path="void-wo",
        icon="block",
        variant=ActionVariant.DANGER,
    )
    def void_wo_row(self, request, object_id):
        wo = self.get_object(request, object_id)
        if wo is None:
            messages.error(request, _("Ordem não encontrada."))
            return HttpResponseRedirect(reverse("admin:craftsman_workorder_changelist"))

        if wo.status not in (WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED):
            messages.warning(request, _("Apenas ordens planned/started podem ser anuladas."))
            return HttpResponseRedirect(reverse("admin:craftsman_workorder_changelist"))

        actor = getattr(request.user, "username", None) or "admin"
        try:
            _void_work_order_from_admin(wo, actor=actor)
            messages.success(
                request,
                _("Ordem %(code)s anulada.") % {"code": wo.ref},
            )
        except Exception as exc:
            messages.error(request, str(exc))

        return HttpResponseRedirect(reverse("admin:craftsman_workorder_changelist"))

    @admin.action(description=_("Finalizar selecionadas"))
    def finish_selected_work_orders(self, request, queryset):
        actor = getattr(request.user, "username", None) or "admin"
        finished = 0
        skipped = 0
        for wo in queryset.filter(status__in=(WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED)):
            try:
                _finish_work_order_from_admin(wo, actor=actor)
                finished += 1
            except Exception as exc:
                skipped += 1
                logger.warning("admin_finish_work_order_failed wo=%s: %s", wo.ref, exc, exc_info=True)
        if finished:
            self.message_user(request, _("%(count)d ordem(ns) finalizada(s).") % {"count": finished})
        if skipped:
            self.message_user(request, _("%(count)d ordem(ns) não puderam ser finalizadas.") % {"count": skipped}, level=messages.WARNING)

    @admin.action(description=_("Cancelar selecionadas"))
    def void_selected_work_orders(self, request, queryset):
        actor = getattr(request.user, "username", None) or "admin"
        voided = 0
        skipped = 0
        for wo in queryset.filter(status__in=(WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED)):
            try:
                _void_work_order_from_admin(wo, actor=actor)
                voided += 1
            except Exception as exc:
                skipped += 1
                logger.warning("admin_void_work_order_failed wo=%s: %s", wo.ref, exc, exc_info=True)
        if voided:
            self.message_user(request, _("%(count)d ordem(ns) cancelada(s).") % {"count": voided})
        if skipped:
            self.message_user(request, _("%(count)d ordem(ns) não puderam ser canceladas.") % {"count": skipped}, level=messages.WARNING)


def _finish_work_order_from_admin(wo: WorkOrder, *, actor: str) -> None:
    """Finish through the operator production facade so Admin matches Backstage."""
    production_service = import_module("shopman.backstage.services.production")

    quantity = wo.started_qty or wo.quantity
    if wo.status == WorkOrder.Status.PLANNED:
        production_service.apply_start(
            work_order_id=wo.pk,
            quantity=quantity,
            position_id="",
            operator_ref=wo.operator_ref or "",
            actor=f"admin:{actor}",
        )
    production_service.apply_finish(
        work_order_id=wo.pk,
        quantity=quantity,
        actor=f"admin:{actor}",
    )


def _void_work_order_from_admin(wo: WorkOrder, *, actor: str) -> str:
    production_service = import_module("shopman.backstage.services.production")

    return production_service.apply_void(
        wo.pk,
        actor=f"admin:{actor}",
        reason="Cancelado via Admin",
    )


def _committed_order_refs(wo: WorkOrder) -> tuple[str, ...]:
    refs = (wo.meta or {}).get("committed_order_refs") or ()
    return tuple(str(ref) for ref in refs if ref)


def _committed_qty_for_work_order(wo: WorkOrder):
    from decimal import Decimal

    refs = _committed_order_refs(wo)
    if not refs:
        return Decimal("0")
    try:
        from shopman.orderman.models import Order

        orders = Order.objects.filter(ref__in=refs).prefetch_related("items")
        total = Decimal("0")
        for order in orders:
            for item in order.items.all():
                if item.sku == wo.output_sku:
                    total += item.qty
        return total
    except Exception:
        logger.debug("admin_work_order_commitments_failed wo=%s", wo.ref, exc_info=True)
        return Decimal("0")
