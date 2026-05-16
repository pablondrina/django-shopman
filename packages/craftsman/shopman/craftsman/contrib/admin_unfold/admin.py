"""
Craftsman Admin with Unfold theme (vNext).

Registers Unfold-styled admin classes for vNext models:
- Technical sheet/BOM (Recipe + RecipeItem inline)
- WorkOrder + WorkOrderItem + WorkOrderEvent inlines

To use, add 'shopman.craftsman.contrib.admin_unfold' to INSTALLED_APPS after 'crafting'.
"""

import logging
from decimal import Decimal
from importlib import import_module
from urllib.parse import urlencode

from django import forms
from django.apps import apps
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from shopman.craftsman.models import (
    Recipe,
    RecipeItem,
    WorkOrder,
    WorkOrderEvent,
    WorkOrderItem,
)
from shopman.utils.contrib.admin_unfold.badges import unfold_badge
from shopman.utils.contrib.admin_unfold.base import (
    BaseModelAdmin,
    BaseTabularInline,
)
from unfold.contrib.filters.admin import ChoicesDropdownFilter, ChoicesRadioFilter, RangeDateFilter
from unfold.decorators import action, display
from unfold.enums import ActionVariant
from unfold.sections import TableSection
from unfold.widgets import (
    UnfoldAdminDecimalFieldWidget,
    UnfoldAdminIntegerFieldWidget,
    UnfoldAdminSelect2Widget,
    UnfoldAdminSelectWidget,
    UnfoldAdminTextareaWidget,
)

logger = logging.getLogger(__name__)

WORK_ORDER_STATUS_PARAM = "status__exact"
WORK_ORDER_DATE_FROM_PARAM = "target_date_from"
WORK_ORDER_DATE_TO_PARAM = "target_date_to"
WORK_ORDER_DATE_HIERARCHY_PARAMS = (
    "target_date__year",
    "target_date__month",
    "target_date__day",
)


# =============================================================================
# TECHNICAL SHEET ADMIN
# =============================================================================


class RecipeItemInlineForm(forms.ModelForm):
    input_sku = forms.ChoiceField(
        label=_("Insumo"),
        required=True,
        widget=UnfoldAdminSelect2Widget(),
    )
    unit = forms.ChoiceField(
        label=_("Unidade"),
        required=True,
        choices=RecipeItem.Unit.choices,
        widget=UnfoldAdminSelectWidget(),
    )

    class Meta:
        model = RecipeItem
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = getattr(self.instance, "input_sku", "") if self.instance else ""
        self.fields["input_sku"].choices = _recipe_input_sku_choices(current)


class RecipeItemInline(BaseTabularInline):
    """Inline for recipe items (insumos)."""

    model = RecipeItem
    form = RecipeItemInlineForm
    verbose_name = _("Ingrediente")
    verbose_name_plural = _("Ingredientes")
    extra = 1
    tab = True
    fields = ("sort_order", "input_sku", "quantity", "unit", "is_optional")
    ordering = ("sort_order", "input_sku")
    ordering_field = "sort_order"
    hide_ordering_field = True


class RecipeAdminForm(forms.ModelForm):
    output_sku = forms.ChoiceField(
        label=_("SKU produzido"),
        required=True,
        widget=UnfoldAdminSelect2Widget(),
        help_text=_("SKU ao qual esta ficha técnica/BOM se aplica. Cadastre o produto antes da ficha."),
    )
    steps_text = forms.CharField(
        label=_("Etapas"),
        required=False,
        widget=UnfoldAdminTextareaWidget(attrs={"rows": 4}),
        help_text=_("Uma etapa por linha, na ordem operacional."),
    )
    max_started_minutes = forms.IntegerField(
        label=_("Tempo alvo iniciado (min)"),
        required=False,
        min_value=1,
        widget=UnfoldAdminIntegerFieldWidget(),
        help_text=_("Após esse tempo uma OP iniciada passa a aparecer como atrasada."),
    )
    capacity_per_day = forms.DecimalField(
        label=_("Capacidade por dia"),
        required=False,
        min_value=0,
        widget=UnfoldAdminDecimalFieldWidget(attrs={"step": "0.001", "min": "0"}),
        help_text=_("Usado no painel para estimar ocupação da produção."),
    )
    requires_batch_tracking = forms.BooleanField(
        label=_("Rastrear lote"),
        required=False,
        help_text=_("Cria um lote ao concluir a produção."),
    )
    shelf_life_days = forms.IntegerField(
        label=_("Validade do lote (dias)"),
        required=False,
        min_value=0,
        widget=UnfoldAdminIntegerFieldWidget(),
        help_text=_("Usado para calcular a validade do lote produzido."),
    )

    class Meta:
        model = Recipe
        exclude = ("steps", "meta")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        meta = self.instance.meta or {}
        current = getattr(self.instance, "output_sku", "") if self.instance else ""
        self.fields["output_sku"].choices = _recipe_output_sku_choices(current)
        self.fields["batch_size"].label = _("Rendimento base")
        self.fields["batch_size"].help_text = _(
            "Quantidade produzida pela ficha técnica base; usada para escalar insumos."
        )
        self.fields["steps_text"].initial = "\n".join(self.instance.steps or [])
        self.fields["max_started_minutes"].initial = meta.get("max_started_minutes")
        self.fields["capacity_per_day"].initial = meta.get("capacity_per_day")
        self.fields["requires_batch_tracking"].initial = bool(meta.get("requires_batch_tracking"))
        self.fields["shelf_life_days"].initial = meta.get("shelf_life_days")

    def clean_steps_text(self) -> list[str]:
        raw = self.cleaned_data.get("steps_text") or ""
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.steps = self.cleaned_data.get("steps_text") or []
        meta = dict(instance.meta or {})
        _set_meta_value(meta, "max_started_minutes", self.cleaned_data.get("max_started_minutes"))
        _set_meta_value(meta, "capacity_per_day", _json_decimal(self.cleaned_data.get("capacity_per_day")))
        _set_meta_value(meta, "requires_batch_tracking", self.cleaned_data.get("requires_batch_tracking") or None)
        _set_meta_value(meta, "shelf_life_days", self.cleaned_data.get("shelf_life_days"))
        instance.meta = meta
        if commit:
            instance.save()
            self.save_m2m()
        return instance


def _recipe_input_sku_choices(current: str = "") -> list[tuple[str, str]]:
    choices: dict[str, str] = {}

    def add(value, label: str = "") -> None:
        value = str(value or "").strip()
        if not value or value in choices:
            return
        choices[value] = label or value

    Product = _optional_model("offerman", "Product")
    if Product is not None:
        for sku, name, unit in Product.objects.order_by("sku").values_list("sku", "name", "unit"):
            unit_label = f" · {unit}" if unit else ""
            add(sku, f"{sku} - {name}{unit_label}")

    for output_sku, name in (
        Recipe.objects.filter(is_active=True)
        .exclude(output_sku="")
        .order_by("output_sku")
        .values_list("output_sku", "name")
    ):
        add(output_sku, f"{output_sku} - {name} (ficha técnica)")

    Ref = _optional_model("refs", "Ref")
    if Ref is not None:
        for value in (
            Ref.objects.filter(ref_type="SKU", is_active=True)
            .order_by("value")
            .values_list("value", flat=True)
        ):
            add(value)

    for value in (
        RecipeItem.objects.exclude(input_sku="")
        .order_by("input_sku")
        .values_list("input_sku", flat=True)
        .distinct()
    ):
        add(value)

    add(current)
    return [("", "---------"), *choices.items()]


def _recipe_output_sku_choices(current: str = "") -> list[tuple[str, str]]:
    choices: dict[str, str] = {}

    def add(value, label: str = "") -> None:
        value = str(value or "").strip()
        if not value or value in choices:
            return
        choices[value] = label or value

    Product = _optional_model("offerman", "Product")
    if Product is not None:
        products = Product.objects.order_by("sku").values_list("sku", "name", "unit")
        for sku, name, unit in products:
            unit_label = f" · {unit}" if unit else ""
            add(sku, f"{sku} - {name}{unit_label}")

    for value in (
        Recipe.objects.exclude(output_sku="")
        .order_by("output_sku")
        .values_list("output_sku", flat=True)
        .distinct()
    ):
        add(value)

    add(current)
    return [("", "---------"), *choices.items()]


def _set_meta_value(meta: dict, key: str, value) -> None:
    if value in (None, "", False):
        meta.pop(key, None)
        return
    meta[key] = value


def _json_decimal(value) -> str | None:
    if value in (None, ""):
        return None
    decimal = Decimal(str(value)).normalize()
    return format(decimal, "f")


def _optional_model(app_label: str, model_name: str):
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        return None


@admin.register(Recipe)
class RecipeAdmin(BaseModelAdmin):
    """Admin interface for technical sheets/BOMs."""

    compressed_fields = True
    warn_unsaved_form = True
    form = RecipeAdminForm

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
            _("BOM"),
            {
                "classes": ["tab"],
                "fields": ("output_sku", "batch_size"),
            },
        ),
        (
            _("Operação"),
            {
                "classes": ["tab"],
                "fields": (
                    "steps_text",
                    ("max_started_minutes", "capacity_per_day"),
                    ("requires_batch_tracking", "shelf_life_days"),
                ),
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


_EVENT_BADGE_COLORS = {
    WorkOrderEvent.Kind.PLANNED: "base",
    WorkOrderEvent.Kind.ADJUSTED: "base",
    WorkOrderEvent.Kind.STARTED: "yellow",
    WorkOrderEvent.Kind.FINISHED: "green",
    WorkOrderEvent.Kind.VOIDED: "red",
}


class WorkOrderEventSection(TableSection):
    related_name = "events"
    fields = ["kind", "quantity", "operator", "created_at"]
    verbose_name = _("Histórico operacional")

    def kind(self, obj):
        color = _EVENT_BADGE_COLORS.get(obj.kind, "base")
        return unfold_badge(obj.get_kind_display(), color)
    kind.short_description = _("Tipo")

    def quantity(self, obj):
        payload = obj.payload or {}
        quantity = (
            payload.get("quantity")
            or payload.get("finished_qty")
            or payload.get("to")
        )
        return _format_work_order_units(quantity)
    quantity.short_description = _("Quantidade")

    def operator(self, obj):
        payload = obj.payload or {}
        return payload.get("operator_ref") or obj.actor or "-"
    operator.short_description = _("Operador")

    def created_at(self, obj):
        return timezone.localtime(obj.created_at).strftime("%d/%m %H:%M")
    created_at.short_description = _("Registrado em")


@admin.register(WorkOrder)
class WorkOrderAdmin(BaseModelAdmin):
    """
    Admin de Execução (vNext).

    4 estados: planned, started, finished, void.
    Campos editáveis: quantity (via adjust enquanto planned), target_date.
    """

    compressed_fields = True
    warn_unsaved_form = True
    list_before_template = "craftsman/admin/workorder_list_before.html"

    list_display = [
        "ref",
        "product_display",
        "date_display",
        "schedule_badge",
        "planned_display",
        "produced_display",
        "commitments_display",
        "status_badge",
    ]

    list_filter = [
        ("status", ChoicesRadioFilter),
        ("recipe", ChoicesDropdownFilter),
        ("target_date", RangeDateFilter),
        "position_ref",
        "operator_ref",
    ]
    list_filter_submit = True
    list_fullwidth = True
    list_horizontal_scrollbar_top = True
    list_per_page = 50
    search_fields = ["ref", "recipe__name", "output_sku"]
    date_hierarchy = "target_date"
    ordering = ["-created_at"]
    autocomplete_fields = ["recipe"]

    inlines = [WorkOrderItemInline, WorkOrderEventInline]
    actions_row = ["production_board_row", "commitments_row", "close_wo_row", "void_wo_row"]
    actions_detail = ["production_board_row", "commitments_row", "close_wo_row", "void_wo_row"]
    actions = ["finish_selected_work_orders", "void_selected_work_orders"]
    list_sections = [WorkOrderEventSection]

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

    @display(description=_("Produto"), ordering="output_sku")
    def product_display(self, obj):
        """Display output product ref."""
        return obj.output_sku or "-"

    @display(description=_("Data agendada"), ordering="target_date")
    def date_display(self, obj):
        """Display target date in DD/MM/YY format."""
        if obj.target_date:
            return obj.target_date.strftime("%d/%m/%y")
        return "-"

    @display(description=_("Agenda"), ordering="target_date")
    def schedule_badge(self, obj):
        """Show the operator-facing timing state for the order."""
        if not obj.target_date:
            return "-"

        today = timezone.localdate()
        if obj.status in (WorkOrder.Status.FINISHED, WorkOrder.Status.VOID):
            return unfold_badge(_("Encerrada"), "base")
        if obj.target_date < today:
            return unfold_badge(_("Atrasada"), "red")
        if obj.target_date == today:
            return unfold_badge(_("Hoje"), "yellow")
        return unfold_badge(_("Programada"), "blue")

    @display(description=_("Planejado"), ordering="quantity")
    def planned_display(self, obj):
        if obj.quantity is not None:
            return _format_work_order_units(obj.quantity)
        return "-"

    @display(description=_("Produzido"), ordering="finished")
    def produced_display(self, obj):
        """Display finished quantity."""
        if obj.finished is not None:
            return _format_work_order_units(obj.finished)
        return "-"

    @display(description=_("Perda"))
    def loss_display(self, obj):
        """Display loss quantity and percentage."""
        loss = obj.loss
        if loss is None:
            return "-"
        if loss == 0:
            return _format_work_order_units(0)

        yield_rate = obj.yield_rate
        loss_pct = (1 - float(yield_rate)) * 100 if yield_rate else 0
        loss_formatted = _format_work_order_units(loss)
        loss_pct_formatted = f"{loss_pct:.1f}".replace(".", ",")

        if loss_pct > 5:
            return f"{loss_formatted} ({loss_pct_formatted}%)"
        return loss_formatted

    @display(description=_("Compromisso"))
    def commitments_display(self, obj):
        refs = _committed_order_refs(obj)
        if not refs:
            return "-"
        qty = _committed_qty_for_work_order(obj)
        return _format_work_order_units(qty)

    @display(description=_("Status"), ordering="status")
    def status_badge(self, obj):
        """Display colored status badge."""
        colors = {
            WorkOrder.Status.PLANNED: "blue",
            WorkOrder.Status.STARTED: "yellow",
            WorkOrder.Status.FINISHED: "green",
            WorkOrder.Status.VOID: "red",
        }
        color = colors.get(obj.status, "base")
        return unfold_badge(_work_order_status_label(obj.status), color)

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
        """Auto-scope the operational changelist to today when no filter is active."""
        has_any_date_param = any(
            request.GET.get(param)
            for param in (
                *WORK_ORDER_DATE_HIERARCHY_PARAMS,
                WORK_ORDER_DATE_FROM_PARAM,
                WORK_ORDER_DATE_TO_PARAM,
            )
        )

        has_admin_nav = any(
            [
                "_changelist_filters" in request.GET,
                "p" in request.GET,
                "o" in request.GET,
                "q" in request.GET,
                WORK_ORDER_STATUS_PARAM in request.GET,
                "recipe__id__exact" in request.GET,
                "position_ref" in request.GET,
                "position_ref__exact" in request.GET,
                "operator_ref" in request.GET,
                "operator_ref__exact" in request.GET,
            ]
        )

        if not has_any_date_param and not has_admin_nav:
            today = timezone.localdate()
            return redirect(
                _work_order_changelist_url(
                    **{
                        WORK_ORDER_DATE_FROM_PARAM: today.isoformat(),
                        WORK_ORDER_DATE_TO_PARAM: today.isoformat(),
                    }
                )
            )

        return super().changelist_view(request, extra_context)

    @action(description=_("Produção"), url_path="production-map", icon="manufacturing")
    def production_board_row(self, request, object_id):
        wo = self.get_object(request, object_id)
        if wo is None:
            messages.error(request, _("Ordem não encontrada."))
            return HttpResponseRedirect(reverse("admin:craftsman_workorder_changelist"))

        if wo.target_date:
            return HttpResponseRedirect(
                f'{reverse("admin_console_production")}?date={wo.target_date.isoformat()}'
            )
        return HttpResponseRedirect(reverse("admin_console_production"))

    @action(description=_("Pedidos"), url_path="commitments", icon="receipt_long")
    def commitments_row(self, request, object_id):
        wo = self.get_object(request, object_id)
        if wo is None:
            messages.error(request, _("Ordem não encontrada."))
            return HttpResponseRedirect(reverse("admin:craftsman_workorder_changelist"))

        return HttpResponseRedirect(
            reverse("admin_console_production_work_order_commitments", args=[wo.ref])
        )

    @action(
        description=_("Concluir"),
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
            messages.warning(request, _("Apenas ordens planejadas/iniciadas podem ser concluídas."))
            return HttpResponseRedirect(reverse("admin:craftsman_workorder_changelist"))

        actor = getattr(request.user, "username", None) or "admin"
        try:
            _finish_work_order_from_admin(wo, actor=actor)
            messages.success(
                request,
                _("Ordem %(code)s concluída (resultado: %(qty)s).") % {
                    "code": wo.ref,
                    "qty": _format_work_order_units(wo.started_qty or wo.quantity),
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

    @admin.action(description=_("Concluir selecionadas"))
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
            self.message_user(request, _("%(count)d ordem(ns) concluída(s).") % {"count": finished})
        if skipped:
            self.message_user(request, _("%(count)d ordem(ns) não puderam ser concluídas.") % {"count": skipped}, level=messages.WARNING)

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


def _work_order_changelist_url(**params) -> str:
    url = reverse("admin:craftsman_workorder_changelist")
    query = urlencode({key: value for key, value in params.items() if value not in (None, "")})
    return f"{url}?{query}" if query else url


def _format_work_order_units(value) -> str:
    if value is None:
        return "-"
    quantity = Decimal(str(value))
    if quantity == quantity.to_integral_value():
        formatted = f"{quantity.quantize(Decimal('1'))}"
    else:
        formatted = f"{quantity.normalize():f}".rstrip("0").rstrip(".")
    return _("%(qty)s un.") % {"qty": formatted.replace(".", ",")}


def _work_order_status_label(status: str) -> str:
    labels = {
        WorkOrder.Status.PLANNED: _("Planejada"),
        WorkOrder.Status.STARTED: _("Iniciada"),
        WorkOrder.Status.FINISHED: _("Concluída"),
        WorkOrder.Status.VOID: _("Cancelada"),
    }
    return str(labels.get(status, status))


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
