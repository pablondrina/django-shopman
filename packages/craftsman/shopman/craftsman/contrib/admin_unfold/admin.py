"""
Craftsman Admin with Unfold theme (vNext).

Registers Unfold-styled admin classes for vNext models:
- Recipe + RecipeItem inline
- WorkOrder + WorkOrderItem + WorkOrderEvent inlines

To use, add 'shopman.craftsman.contrib.admin_unfold' to INSTALLED_APPS after 'crafting'.
"""

import logging

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from unfold.contrib.filters.admin.datetime_filters import RangeDateFilter
from unfold.contrib.filters.admin.dropdown_filters import ChoicesDropdownFilter
from unfold.decorators import action, display
from unfold.enums import ActionVariant
from unfold.sections import TableSection

from shopman.utils.contrib.admin_unfold.badges import unfold_badge, unfold_badge_numeric
from shopman.utils.contrib.admin_unfold.base import (
    BaseModelAdmin,
    BaseStackedInline,
    BaseTabularInline,
)
from shopman.utils.formatting import format_quantity

from shopman.craftsman.models import (
    Recipe,
    RecipeItem,
    WorkOrder,
    WorkOrderEvent,
    WorkOrderItem,
)

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
                "fields": ("input_ref", "quantity", "unit"),
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
        "code",
        "name",
        "output_ref",
        "batch_size",
        "is_active",
    ]
    list_filter = ["is_active"]
    search_fields = ["code", "name", "output_ref"]
    ordering = ["name"]
    prepopulated_fields = {"code": ("name",)}

    inlines = [RecipeItemInline]

    fieldsets = (
        (
            _("Identificação"),
            {"fields": ("code", "name", "is_active")},
        ),
        (
            _("Produção"),
            {
                "classes": ["tab"],
                "fields": ("output_ref", "batch_size"),
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

    3 estados: open, done, void.
    Campos editáveis: quantity (via adjust), scheduled_date.
    """

    compressed_fields = True
    warn_unsaved_form = True

    list_display = [
        "ref",
        "product_display",
        "date_display",
        "preorder_indicator",
        "quantity",
        "produced_display",
        "loss_display",
        "status_badge",
    ]

    list_filter = [
        "status",
        ("recipe", ChoicesDropdownFilter),
        ("scheduled_date", RangeDateFilter),
    ]
    list_filter_submit = True
    search_fields = ["ref", "recipe__name", "output_ref"]
    date_hierarchy = "scheduled_date"
    ordering = ["-created_at"]
    autocomplete_fields = ["recipe"]

    inlines = [WorkOrderItemInline, WorkOrderEventInline]
    actions_row = ["close_wo_row", "void_wo_row"]
    actions_detail = ["close_wo_row", "void_wo_row"]
    list_sections = [WorkOrderItemSection]

    fieldsets = (
        (
            _("Identificação"),
            {"fields": ("ref", "recipe", "output_ref", "status")},
        ),
        (
            _("Quantidades"),
            {
                "classes": ["tab"],
                "fields": ("quantity", "produced"),
            },
        ),
        (
            _("Agendamento"),
            {
                "classes": ["tab"],
                "fields": ("scheduled_date", "started_at", "finished_at"),
            },
        ),
        (
            _("Referências"),
            {
                "classes": ["tab"],
                "fields": ("source_ref", "position_ref", "assigned_ref"),
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
        "output_ref",
        "status",
        "produced",
        "rev",
        "started_at",
        "finished_at",
    ]

    @display(description=_("Produto"))
    def product_display(self, obj):
        """Display output product ref."""
        return obj.output_ref or "-"

    @display(description=_("Data"))
    def date_display(self, obj):
        """Display date in DD/MM/YY format."""
        if obj.scheduled_date:
            return obj.scheduled_date.strftime("%d/%m/%y")
        return "-"

    @display(description=_("Tipo"))
    def preorder_indicator(self, obj):
        """Show badge if WorkOrder is scheduled for a future date (preorder/programado)."""
        if obj.scheduled_date and obj.scheduled_date > timezone.localdate():
            return unfold_badge(_("Programado"), "purple")
        return ""

    @display(description=_("Produzido"))
    def produced_display(self, obj):
        """Display produced quantity."""
        if obj.produced is not None:
            return unfold_badge_numeric(format_quantity(obj.produced), "green")
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

    @display(description=_("Status"))
    def status_badge(self, obj):
        """Display colored status badge."""
        colors = {
            WorkOrder.Status.OPEN: "blue",
            WorkOrder.Status.DONE: "green",
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

    def changelist_view(self, request, extra_context=None):
        """Auto-redirect to today if no date filter."""
        date_year = request.GET.get("scheduled_date__year")
        date_month = request.GET.get("scheduled_date__month")
        date_day = request.GET.get("scheduled_date__day")

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
                f"scheduled_date__year={today.year}&"
                f"scheduled_date__month={today.month}&"
                f"scheduled_date__day={today.day}"
            )

        return super().changelist_view(request, extra_context)

    @action(
        description=_("Concluir ✓"),
        url_path="close-wo",
        icon="check_circle",
        variant=ActionVariant.SUCCESS,
    )
    def close_wo_row(self, request, object_id):
        wo = self.get_object(request, object_id)
        if wo is None:
            messages.error(request, _("Ordem não encontrada."))
            return HttpResponseRedirect(reverse("admin:craftsman_workorder_changelist"))

        if wo.status != WorkOrder.Status.OPEN:
            messages.warning(request, _("Apenas ordens abertas podem ser encerradas."))
            return HttpResponseRedirect(reverse("admin:craftsman_workorder_changelist"))

        from shopman.craftsman import craft

        actor = getattr(request.user, "username", None) or "admin"
        try:
            craft.close(wo, produced=wo.quantity, actor=actor)
            messages.success(
                request,
                _("Ordem %(code)s encerrada (produzido: %(qty)s).") % {
                    "code": wo.ref,
                    "qty": format_quantity(wo.quantity),
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

        if wo.status != WorkOrder.Status.OPEN:
            messages.warning(request, _("Apenas ordens abertas podem ser anuladas."))
            return HttpResponseRedirect(reverse("admin:craftsman_workorder_changelist"))

        from shopman.craftsman import craft

        actor = getattr(request.user, "username", None) or "admin"
        try:
            craft.void(wo, reason="Anulado via admin", actor=actor)
            messages.success(
                request,
                _("Ordem %(code)s anulada.") % {"code": wo.ref},
            )
        except Exception as exc:
            messages.error(request, str(exc))

        return HttpResponseRedirect(reverse("admin:craftsman_workorder_changelist"))
