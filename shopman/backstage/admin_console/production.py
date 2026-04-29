"""Production pilot page rendered inside the Unfold Admin shell."""

from __future__ import annotations

import json

from django import forms
from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from unfold.widgets import (
    UnfoldAdminDecimalFieldWidget,
    UnfoldAdminSelectWidget,
    UnfoldAdminSingleDateWidget,
    UnfoldAdminTextInputWidget,
)

from shopman.backstage.projections.production import resolve_production_access
from shopman.backstage.services import production as production_service
from shopman.backstage.views.production import (
    handle_production_post,
    render_production_surface,
)

TEMPLATE = "admin_console/production/index.html"
BULK_RESULT_TEMPLATE = "admin_console/production/partials/bulk_create_result.html"


class ProductionFilterForm(forms.Form):
    date = forms.DateField(
        label="Data",
        required=False,
        widget=UnfoldAdminSingleDateWidget(attrs={"class": "max-w-none"}),
    )
    position_ref = forms.ChoiceField(
        label="Posto",
        required=False,
        widget=UnfoldAdminSelectWidget(attrs={"class": "max-w-none"}),
    )
    operator_ref = forms.CharField(
        label="Responsavel",
        required=False,
        widget=UnfoldAdminTextInputWidget(
            attrs={"class": "max-w-none", "placeholder": "Nome ou usuario"}
        ),
    )
    base_recipe = forms.ChoiceField(
        label="Receita-base",
        required=False,
        widget=UnfoldAdminSelectWidget(attrs={"class": "max-w-none"}),
    )

    def __init__(self, *args, position_choices=(), base_recipe_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["position_ref"].choices = position_choices
        self.fields["base_recipe"].choices = base_recipe_choices


class ProductionStartForm(forms.Form):
    action = forms.CharField(widget=forms.HiddenInput(), initial="start")
    wo_id = forms.CharField(widget=forms.HiddenInput())
    target_date = forms.CharField(widget=forms.HiddenInput())
    position_ref = forms.CharField(widget=forms.HiddenInput(), required=False)
    operator_ref_filter = forms.CharField(widget=forms.HiddenInput(), required=False)
    base_recipe = forms.CharField(widget=forms.HiddenInput(), required=False)
    quantity = forms.DecimalField(
        label="Quantidade iniciada",
        min_value=0,
        widget=UnfoldAdminDecimalFieldWidget(
            attrs={"step": "0.001", "min": "0.001", "inputmode": "decimal"}
        ),
    )
    position = forms.ChoiceField(
        label="Destino",
        required=False,
        widget=UnfoldAdminSelectWidget(),
    )
    operator_ref = forms.CharField(
        label="Responsavel",
        required=False,
        widget=UnfoldAdminTextInputWidget(attrs={"placeholder": "Opcional"}),
    )

    def __init__(self, *args, position_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["position"].choices = position_choices


class ProductionPlanForm(forms.Form):
    action = forms.CharField(widget=forms.HiddenInput(), initial="set_planned")
    target_date = forms.CharField(widget=forms.HiddenInput())
    position_ref = forms.CharField(widget=forms.HiddenInput(), required=False)
    operator_ref = forms.CharField(widget=forms.HiddenInput(), required=False)
    operator_ref_filter = forms.CharField(widget=forms.HiddenInput(), required=False)
    base_recipe = forms.CharField(widget=forms.HiddenInput(), required=False)
    recipe = forms.CharField(widget=forms.HiddenInput())
    quantity = forms.DecimalField(
        label="Planejado",
        min_value=0,
        max_value=9999,
        widget=UnfoldAdminDecimalFieldWidget(
            attrs={
                "class": "max-w-24 text-right tabular-nums",
                "step": "0.001",
                "min": "0",
                "max": "9999",
                "inputmode": "decimal",
            }
        ),
    )


class ProductionFinishForm(forms.Form):
    action = forms.CharField(widget=forms.HiddenInput(), initial="finish")
    wo_id = forms.CharField(widget=forms.HiddenInput())
    target_date = forms.CharField(widget=forms.HiddenInput())
    position_ref = forms.CharField(widget=forms.HiddenInput(), required=False)
    operator_ref_filter = forms.CharField(widget=forms.HiddenInput(), required=False)
    base_recipe = forms.CharField(widget=forms.HiddenInput(), required=False)
    quantity = forms.DecimalField(
        label="Quantidade concluida",
        min_value=0,
        widget=UnfoldAdminDecimalFieldWidget(
            attrs={"step": "0.001", "min": "0.001", "inputmode": "decimal"}
        ),
    )


class ProductionQuickFinishForm(forms.Form):
    action = forms.CharField(widget=forms.HiddenInput(), initial="quick_finish")
    target_date = forms.CharField(widget=forms.HiddenInput())
    position_ref = forms.CharField(widget=forms.HiddenInput(), required=False)
    operator_ref_filter = forms.CharField(widget=forms.HiddenInput(), required=False)
    base_recipe = forms.CharField(widget=forms.HiddenInput(), required=False)
    recipe = forms.ChoiceField(
        label="Receita",
        widget=UnfoldAdminSelectWidget(attrs={"class": "max-w-none"}),
    )
    quantity = forms.DecimalField(
        label="Quantidade concluida",
        min_value=0,
        widget=UnfoldAdminDecimalFieldWidget(
            attrs={"class": "max-w-none", "step": "0.001", "min": "0.001", "inputmode": "decimal"}
        ),
    )
    position = forms.ChoiceField(
        label="Destino",
        required=False,
        widget=UnfoldAdminSelectWidget(attrs={"class": "max-w-none"}),
    )

    def __init__(self, *args, recipe_choices=(), position_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["recipe"].choices = recipe_choices
        self.fields["position"].choices = position_choices


def production_console_view(request: HttpRequest) -> HttpResponse:
    """Render the production board as an Admin/Unfold custom operational page."""
    request.current_app = admin.site.name

    access = resolve_production_access(request.user)
    if not access.can_access_board:
        messages.error(request, "Sem permissao para acessar producao.")
        return HttpResponseRedirect(reverse("admin:index"))

    if request.method == "POST":
        return handle_production_post(
            request,
            access,
            redirect_url_name="admin_console_production",
        )

    context = {
        **admin.site.each_context(request),
        "title": "Producao",
        "subtitle": "Piloto Admin/Unfold",
        "pilot_mode": True,
        "legacy_production_url": reverse("backstage:production"),
        "work_orders_url": reverse("admin:craftsman_workorder_changelist"),
        "reports_url": reverse("backstage:production_reports"),
        "dashboard_url": reverse("backstage:production_dashboard"),
        "bulk_create_url": reverse("admin_console_production_bulk_create"),
    }
    return render_production_surface(
        request,
        access,
        template_name=TEMPLATE,
        extra_context=context,
        context_callback=build_production_console_context,
    )


def build_production_console_context(request: HttpRequest, board, context: dict) -> dict:
    """Build Unfold component data for the production pilot page."""
    return {
        "production_filter_form": _filter_form(board),
        "production_quick_finish_form": _quick_finish_form(board),
        "production_navigation": _navigation(context),
        "production_kpis": _kpis(board),
        "production_matrix_table": _matrix_table(request, board, context),
        "production_history_table": _history_table(board),
    }


def production_console_bulk_create_view(request: HttpRequest) -> HttpResponse:
    """Create suggested work orders from the Admin/Unfold pilot page."""
    if request.method != "POST":
        return HttpResponse("Method not allowed", status=405)

    access = resolve_production_access(request.user)
    if not (access.can_manage_all or access.can_edit_planned):
        return HttpResponseForbidden("Voce nao tem permissao para esta acao.")

    if request.content_type == "application/json":
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return _bulk_result(request, error="Dados invalidos", status=400)
        target_date_str = body.get("date")
        orders_data = body.get("orders", [])
    else:
        target_date_str = request.POST.get("date")
        recipe_refs = request.POST.getlist("recipe_ref")
        quantities = request.POST.getlist("quantity")
        orders_data = [
            {"recipe_ref": recipe_ref, "quantity": quantity}
            for recipe_ref, quantity in zip(recipe_refs, quantities, strict=False)
        ]

    if not orders_data:
        return _bulk_result(request, error="Nenhuma ordem informada", status=422)

    result = production_service.apply_suggestions(
        target_date_value=target_date_str,
        entries=orders_data,
    )
    return _bulk_result(
        request,
        created=result.created,
        errors=result.errors,
        target_date=result.target_date,
    )


def _bulk_result(
    request: HttpRequest,
    *,
    created=None,
    errors=None,
    target_date=None,
    error: str | None = None,
    status: int = 200,
) -> HttpResponse:
    return HttpResponse(
        render_to_string(
            BULK_RESULT_TEMPLATE,
            {
                "created": created or [],
                "errors": errors or [],
                "target_date": target_date,
                "error": error,
            },
            request=request,
        ),
        status=status,
    )


def _navigation(context: dict) -> list[dict]:
    return [
        {
            "title": "Painel",
            "icon": "manufacturing",
            "link": reverse("admin_console_production"),
            "active": True,
        },
        {
            "title": "Ordens",
            "icon": "assignment",
            "link": context["work_orders_url"],
        },
        {
            "title": "Dashboard atual",
            "icon": "monitoring",
            "link": context["dashboard_url"],
        },
        {
            "title": "UI atual",
            "icon": "open_in_new",
            "link": context["legacy_production_url"],
        },
    ]


def _kpis(board) -> tuple[dict, ...]:
    counts = board.counts
    return (
        {
            "title": "Planejado",
            "value": counts.planned_qty,
            "footer": f"{counts.planned} OPs",
            "icon": "event_note",
        },
        {
            "title": "Em producao",
            "value": counts.started_qty,
            "footer": f"{counts.started} OPs",
            "icon": "timer",
        },
        {
            "title": "Concluido",
            "value": counts.finished_qty,
            "footer": f"{counts.finished} OPs",
            "icon": "done_all",
        },
        {
            "title": "Perda",
            "value": counts.loss_qty,
            "footer": f"{counts.total} OPs no dia",
            "icon": "warning",
        },
    )


def _matrix_table(request: HttpRequest, board, context: dict) -> dict:
    access = board.access
    headers = ["SKU"]
    rows = []

    if access.can_view_planned:
        headers.append("Planejado")
    if access.can_view_started:
        headers.extend(["Iniciar", "Em producao"])
    if access.can_view_finished:
        headers.extend(["Concluir", "Concluido", "Perda"])

    for group in board.matrix_groups:
        for group_row in group.rows:
            row = group_row.row
            usage = group_row.usage
            cols = [
                _cell(request, "sku", row=row, usage=usage, group=group, context=context),
            ]
            if access.can_view_planned:
                cols.append(_cell(request, "planned", row=row, context=context, form=_plan_form(row, board)))
            if access.can_view_started:
                cols.extend([
                    _cell(
                        request,
                        "start",
                        row=row,
                        context=context,
                        entries=_start_entries(row, board),
                    ),
                    _cell(request, "started", row=row),
                ])
            if access.can_view_finished:
                cols.extend([
                    _cell(
                        request,
                        "finish",
                        row=row,
                        context=context,
                        entries=_finish_entries(row, board),
                    ),
                    row.finished_qty or "0",
                    row.loss_qty or "0",
                ])

            rows.append({
                "cols": cols,
                "table": _details_table(row, access=access),
            })

    return {
        "collapsible": True,
        "headers": headers,
        "rows": rows,
    }


def _details_table(row, *, access) -> dict:
    detail_rows = [
        [
            "Receita",
            row.output_sku,
            "-",
            "-",
            row.recipe_name,
        ]
    ]

    if row.suggestion and (access.can_view_suggested or access.can_edit_suggested):
        detail_rows.append([
            "Sugestao",
            row.suggestion.recipe_ref,
            row.suggestion.quantity,
            row.suggestion.committed or "-",
            f"Media {row.suggestion.avg_demand} - {row.suggestion.confidence}",
        ])

    for usage in row.base_usages:
        detail_rows.append([
            "Receita-base",
            usage.ref,
            usage.quantity_display,
            "-",
            f"{usage.per_unit_display}/un.",
        ])

    if access.can_view_planned:
        for item in row.planned_orders:
            detail_rows.append([
                "Planejada",
                item.ref,
                item.planned_qty,
                item.committed_qty or "-",
                _commitments(item),
            ])
    if access.can_view_started:
        for item in row.started_orders:
            detail_rows.append([
                "Em producao",
                item.ref,
                item.started_qty,
                item.committed_qty or "-",
                item.operator_ref or "-",
            ])
    if access.can_view_finished:
        for item in row.finished_orders:
            detail_rows.append([
                "Concluida",
                item.ref,
                item.finished_qty,
                item.committed_qty or "-",
                f"Perda {item.loss}" if item.loss else "-",
            ])

    if not detail_rows:
        detail_rows.append(["Sem OP", row.output_sku, "-", "-", "Sem detalhes para os filtros atuais."])

    return {
        "collapsible": True,
        "headers": ["Estado", "OP", "Qtd", "Comprometido", "Detalhe"],
        "rows": detail_rows,
    }


def _history_table(board) -> dict:
    access = board.access
    headers = ["Ordem", "Produto", "Status"]
    if access.can_view_planned:
        headers.append("Planejado")
    if access.can_view_started:
        headers.append("Iniciado")
    if access.can_view_finished:
        headers.extend(["Concluido", "Perda"])

    rows = []
    for wo in board.work_orders:
        cols = [
            wo.ref,
            wo.output_sku,
            format_html(
                '<span class="rounded-default px-2 py-1 text-xs font-semibold {}">{}</span>',
                wo.status_color,
                wo.status_label,
            ),
        ]
        if access.can_view_planned:
            cols.append(wo.planned_qty)
        if access.can_view_started:
            cols.append(wo.started_qty or "-")
        if access.can_view_finished:
            cols.extend([wo.finished_qty or "-", wo.loss or "-"])
        rows.append(cols)

    return {
        "headers": headers,
        "rows": rows,
    }


def _filter_form(board) -> ProductionFilterForm:
    return ProductionFilterForm(
        initial={
            "date": board.selected_date,
            "position_ref": board.selected_position_ref,
            "operator_ref": board.selected_operator_ref,
            "base_recipe": board.selected_base_recipe,
        },
        position_choices=[("", "Todos"), *[(position.ref, position.name) for position in board.positions]],
        base_recipe_choices=[
            ("", "Todas"),
            *[(recipe.output_sku, f"{recipe.name} ({recipe.count})") for recipe in board.base_recipes],
        ],
    )


def _quick_finish_form(board) -> ProductionQuickFinishForm:
    return ProductionQuickFinishForm(
        initial={
            "target_date": board.selected_date,
            "position_ref": board.selected_position_ref,
            "operator_ref_filter": board.selected_operator_ref,
            "base_recipe": board.selected_base_recipe,
            "position": board.default_position_pk or "",
        },
        recipe_choices=[(recipe.pk, f"{recipe.ref} - {recipe.name}") for recipe in board.recipes],
        position_choices=_position_pk_choices(board),
    )


def _plan_form(row, board) -> ProductionPlanForm | None:
    if not row.recipe_pk:
        return None
    return ProductionPlanForm(
        initial={
            "action": "set_planned",
            "target_date": board.selected_date,
            "position_ref": board.selected_position_ref,
            "operator_ref": board.selected_operator_ref,
            "operator_ref_filter": board.selected_operator_ref,
            "base_recipe": board.selected_base_recipe,
            "recipe": row.recipe_pk,
            "quantity": row.planned_qty,
        }
    )


def _start_entries(row, board) -> list[dict]:
    return [
        {
            "item": item,
            "modal_title": f"Iniciar {item.output_sku}",
            "modal_description": "Informe a quantidade que entrou fisicamente em producao.",
            "submit_label": "Iniciar",
            "form": ProductionStartForm(
                initial={
                    "action": "start",
                    "wo_id": item.pk,
                    "target_date": board.selected_date,
                    "position_ref": board.selected_position_ref,
                    "operator_ref_filter": board.selected_operator_ref,
                    "base_recipe": board.selected_base_recipe,
                    "quantity": item.planned_qty,
                    "position": board.default_position_pk or "",
                    "operator_ref": item.operator_ref or board.selected_operator_ref,
                },
                position_choices=_position_pk_choices(board),
            ),
        }
        for item in row.planned_orders
    ]


def _finish_entries(row, board) -> list[dict]:
    return [
        {
            "item": item,
            "modal_title": f"Concluir {item.output_sku}",
            "modal_description": "Informe o acabado real. A perda sai da diferenca para o iniciado.",
            "submit_label": "Concluir",
            "form": ProductionFinishForm(
                initial={
                    "action": "finish",
                    "wo_id": item.pk,
                    "target_date": board.selected_date,
                    "position_ref": board.selected_position_ref,
                    "operator_ref_filter": board.selected_operator_ref,
                    "base_recipe": board.selected_base_recipe,
                    "quantity": item.started_qty,
                }
            ),
        }
        for item in row.started_orders
    ]


def _position_pk_choices(board) -> list[tuple[str | int, str]]:
    return [("", "Padrao"), *[(position.pk, position.name) for position in board.positions]]


def _commitments(item):
    if not item.order_commitments:
        return "-"
    chunks = [
        f"#{commitment.ref}: {commitment.qty_required}"
        for commitment in item.order_commitments
    ]
    return ", ".join(chunks)


def _cell(request: HttpRequest, name: str, **context):
    return mark_safe(
        render_to_string(
            f"admin_console/production/cells/{name}.html",
            context,
            request=request,
        )
    )
