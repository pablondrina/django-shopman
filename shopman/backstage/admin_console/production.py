"""Projection-backed production Admin pages rendered inside the Unfold shell."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseRedirect,
    StreamingHttpResponse,
)
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.generic import TemplateView
from shopman.craftsman.models import Recipe, WorkOrder
from unfold.views import UnfoldModelAdminViewMixin
from unfold.widgets import (
    UnfoldAdminDecimalFieldWidget,
    UnfoldAdminSelectWidget,
    UnfoldAdminSingleDateWidget,
    UnfoldAdminTextInputWidget,
)

from shopman.backstage.projections.production import (
    build_production_dashboard,
    build_production_reports,
    build_production_weighing,
    resolve_production_access,
)
from shopman.backstage.services import production as production_service
from shopman.backstage.views.production import (
    _can_view_reports,
    _report_filters,
    handle_production_post,
    render_production_surface,
)

TEMPLATE = "admin_console/production/index.html"
PLANNING_TEMPLATE = "admin_console/production/planning.html"
DASHBOARD_TEMPLATE = "admin_console/production/dashboard.html"
REPORTS_TEMPLATE = "admin_console/production/reports.html"
WEIGHING_TEMPLATE = "admin_console/production/weighing.html"
COMMITMENTS_TEMPLATE = "admin_console/production/commitments.html"
BULK_RESULT_TEMPLATE = "admin_console/production/partials/bulk_create_result.html"
STATUS_FILTER_PARAM = "status__exact"
REPORT_KIND_CHOICES = (
    ("history", "Histórico de ordens"),
    ("operator_productivity", "Produtividade"),
    ("recipe_waste", "Desperdício"),
)
REPORT_STATUS_CHOICES = (
    ("", "Todos"),
    (WorkOrder.Status.PLANNED, "Planejada"),
    (WorkOrder.Status.STARTED, "Iniciada"),
    (WorkOrder.Status.FINISHED, "Concluída"),
    (WorkOrder.Status.VOID, "Cancelada"),
)
PLAN_ADJUST_REASON_CHOICES = (
    ("demand", "Demanda atualizada"),
    ("commitment", "Encomenda/compromisso"),
    ("capacity", "Capacidade do dia"),
    ("materials", "Disponibilidade de insumos"),
)


class ProductionDashboardFilterForm(forms.Form):
    date = forms.DateField(
        label="Data agendada",
        required=False,
        widget=UnfoldAdminSingleDateWidget(attrs={"class": "max-w-none"}),
    )
    position_ref = forms.ChoiceField(
        label="Posto",
        required=False,
        widget=UnfoldAdminSelectWidget(attrs={"class": "max-w-none"}),
    )

    def __init__(self, *args, position_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["position_ref"].choices = position_choices


class ProductionReportsFilterForm(forms.Form):
    report_kind = forms.ChoiceField(
        label="Relatório",
        choices=REPORT_KIND_CHOICES,
        required=False,
        widget=forms.HiddenInput(),
    )
    date_from = forms.DateField(
        label="De",
        required=False,
        widget=UnfoldAdminSingleDateWidget(attrs={"class": "max-w-none"}),
    )
    date_to = forms.DateField(
        label="Até",
        required=False,
        widget=UnfoldAdminSingleDateWidget(attrs={"class": "max-w-none"}),
    )
    recipe_ref = forms.ChoiceField(
        label="Ficha técnica",
        required=False,
        widget=UnfoldAdminSelectWidget(attrs={"class": "max-w-none"}),
    )
    position_ref = forms.ChoiceField(
        label="Posto",
        required=False,
        widget=UnfoldAdminSelectWidget(attrs={"class": "max-w-none"}),
    )
    operator_ref = forms.CharField(
        label="Operador",
        required=False,
        widget=UnfoldAdminTextInputWidget(attrs={"class": "max-w-none"}),
    )
    status = forms.ChoiceField(
        label="Status",
        choices=REPORT_STATUS_CHOICES,
        required=False,
        widget=UnfoldAdminSelectWidget(attrs={"class": "max-w-none"}),
    )

    def __init__(self, *args, recipe_choices=(), position_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["recipe_ref"].choices = recipe_choices
        self.fields["position_ref"].choices = position_choices


class ProductionWeighingFilterForm(forms.Form):
    date = forms.DateField(
        label="Data agendada",
        required=False,
        widget=UnfoldAdminSingleDateWidget(attrs={"class": "max-w-none"}),
    )
    position_ref = forms.ChoiceField(
        label="Posto",
        required=False,
        widget=UnfoldAdminSelectWidget(attrs={"class": "max-w-none"}),
    )
    base_recipe = forms.ChoiceField(
        label="Ficha-base",
        required=False,
        widget=UnfoldAdminSelectWidget(attrs={"class": "max-w-none"}),
    )

    def __init__(self, *args, position_choices=(), base_recipe_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["position_ref"].choices = position_choices
        self.fields["base_recipe"].choices = base_recipe_choices


class ProductionFilterForm(forms.Form):
    date = forms.DateField(
        label="Data agendada",
        required=False,
        widget=UnfoldAdminSingleDateWidget(attrs={"class": "max-w-none"}),
    )
    position_ref = forms.ChoiceField(
        label="Posto",
        required=False,
        widget=UnfoldAdminSelectWidget(attrs={"class": "max-w-none"}),
    )
    operator_ref = forms.CharField(
        label="Responsável",
        required=False,
        widget=UnfoldAdminTextInputWidget(
            attrs={"class": "max-w-none", "placeholder": "Nome ou usuário"}
        ),
    )
    base_recipe = forms.ChoiceField(
        label="Ficha-base",
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
        label="Responsável",
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
                "class": "max-w-none",
                "step": "0.001",
                "min": "0",
                "max": "9999",
                "inputmode": "decimal",
            }
        ),
    )


class ProductionPlanAdjustForm(ProductionPlanForm):
    reason = forms.ChoiceField(
        label="Motivo",
        choices=PLAN_ADJUST_REASON_CHOICES,
        required=True,
        widget=UnfoldAdminSelectWidget(attrs={"class": "max-w-none"}),
    )


class ProductionFinishForm(forms.Form):
    action = forms.CharField(widget=forms.HiddenInput(), initial="finish")
    wo_id = forms.CharField(widget=forms.HiddenInput())
    target_date = forms.CharField(widget=forms.HiddenInput())
    position_ref = forms.CharField(widget=forms.HiddenInput(), required=False)
    operator_ref_filter = forms.CharField(widget=forms.HiddenInput(), required=False)
    base_recipe = forms.CharField(widget=forms.HiddenInput(), required=False)
    quantity = forms.DecimalField(
        label="Quantidade concluída",
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
        label="Ficha técnica",
        widget=UnfoldAdminSelectWidget(attrs={"class": "max-w-none"}),
    )
    quantity = forms.DecimalField(
        label="Quantidade concluída",
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


class ProductionConsoleView(UnfoldModelAdminViewMixin, TemplateView):
    """Production orders page rendered through the official Unfold custom-page mixin."""

    template_name = TEMPLATE
    title = "Produção"
    permission_required: tuple[str, ...] = ()

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        self.access = resolve_production_access(request.user)
        if not self.access.can_access_board:
            messages.error(request, "Sem permissão para acessar produção.")
            return HttpResponseRedirect(reverse("admin:index"))
        return super().dispatch(request, *args, **kwargs)

    def has_permission(self) -> bool:
        access = getattr(self, "access", None)
        if access is None:
            access = resolve_production_access(self.request.user)
        return access.can_access_board

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        return handle_production_post(
            request,
            self.access,
            redirect_url_name="admin_console_production",
        )

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        return render_production_surface(
            request,
            self.access,
            template_name=self.template_name,
            extra_context=self.get_context_data(**kwargs),
            context_callback=build_production_console_context,
        )


class ProductionPlanningView(UnfoldModelAdminViewMixin, TemplateView):
    """Projection-backed production planning page inside the Admin shell."""

    template_name = PLANNING_TEMPLATE
    title = "Planejamento"
    permission_required: tuple[str, ...] = ()

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        self.access = resolve_production_access(request.user)
        if not self.access.can_access_board:
            messages.error(request, "Sem permissão para acessar planejamento de produção.")
            return HttpResponseRedirect(reverse("admin:index"))
        return super().dispatch(request, *args, **kwargs)

    def has_permission(self) -> bool:
        access = getattr(self, "access", None)
        if access is None:
            access = resolve_production_access(self.request.user)
        return access.can_access_board

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        return handle_production_post(
            request,
            self.access,
            redirect_url_name="admin_console_production_planning",
        )

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        return render_production_surface(
            request,
            self.access,
            template_name=self.template_name,
            extra_context=self.get_context_data(**kwargs),
            context_callback=build_production_planning_context,
        )


class ProductionDashboardView(UnfoldModelAdminViewMixin, TemplateView):
    """Projection-backed production dashboard inside the Admin shell."""

    template_name = DASHBOARD_TEMPLATE
    title = "Painel de produção"
    permission_required: tuple[str, ...] = ()

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        self.access = resolve_production_access(request.user)
        if not self.access.can_access_board:
            messages.error(request, "Sem permissão para acessar produção.")
            return HttpResponseRedirect(reverse("admin:index"))
        return super().dispatch(request, *args, **kwargs)

    def has_permission(self) -> bool:
        access = getattr(self, "access", None)
        if access is None:
            access = resolve_production_access(self.request.user)
        return access.can_access_board

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        selected_date = _dashboard_selected_date(self.request)
        position_ref = (self.request.GET.get("position_ref") or "").strip()
        dashboard = build_production_dashboard(
            selected_date=selected_date,
            position_ref=position_ref,
        )
        filter_form = _dashboard_filter_form(
            selected_date=selected_date,
            position_ref=position_ref,
        )
        context.update({
            "production_dashboard": dashboard,
            "production_dashboard_filter_form": filter_form,
            "production_dashboard_filter_fields": _form_fields(filter_form, "date", "position_ref"),
            "production_flow_tabs": _production_flow_tabs(selected_date, active="dashboard"),
            "production_dashboard_links": _admin_production_links(selected_date),
            "production_dashboard_kpis": _dashboard_kpis(dashboard, selected_date),
            "production_dashboard_late_table": _dashboard_late_table(dashboard),
            "production_dashboard_reset_url": reverse("admin_console_production_dashboard"),
        })
        return context


class ProductionReportsView(UnfoldModelAdminViewMixin, TemplateView):
    """Projection-backed production reports inside the Admin shell."""

    template_name = REPORTS_TEMPLATE
    title = "Relatórios de produção"
    permission_required: tuple[str, ...] = ()

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not _can_view_reports(request.user):
            messages.error(request, "Sem permissão para acessar relatórios de produção.")
            return HttpResponseRedirect(reverse("admin:index"))
        return super().dispatch(request, *args, **kwargs)

    def has_permission(self) -> bool:
        return _can_view_reports(self.request.user)

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        filters = _report_filters(request)
        if request.GET.get("format") == "csv":
            csv_bytes = production_service.export_reports_csv(filters["report_kind"], filters)
            response = StreamingHttpResponse(
                [csv_bytes],
                content_type="text/csv; charset=utf-8",
            )
            filename = f"producao_{filters['report_kind']}_{filters['date_from']}_{filters['date_to']}.csv"
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response
        self.reports = build_production_reports(filters)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        reports = getattr(self, "reports", None)
        if reports is None:
            reports = build_production_reports(_report_filters(self.request))
        filter_form = _reports_filter_form(reports)
        context.update({
            "production_reports": reports,
            "production_reports_filter_form": filter_form,
            "production_reports_filter_fields": _form_fields(
                filter_form,
                "date_from",
                "date_to",
                "recipe_ref",
                "position_ref",
                "operator_ref",
                "status",
            ),
            "production_flow_tabs": _production_flow_tabs(reports.filters.date_to, active="reports"),
            "production_reports_links": _admin_production_links(reports.filters.date_to),
            "production_reports_tabs": _reports_tabs(reports.filters),
            "production_reports_filter_summary": _reports_filter_summary(reports.filters),
            "production_reports_table": _reports_table(reports),
            "production_reports_title": _reports_title(reports.filters.report_kind),
            "production_reports_csv_url": _reports_csv_url(reports.filters),
            "production_reports_reset_url": reverse("admin_console_production_reports"),
            "production_reports_filter_reset_url": _reports_filter_reset_url(reports.filters),
        })
        return context


class ProductionWeighingView(UnfoldModelAdminViewMixin, TemplateView):
    """Projection-backed thermal weighing tickets inside the Admin shell."""

    template_name = WEIGHING_TEMPLATE
    title = "Filipetas de pesagem"
    permission_required: tuple[str, ...] = ()

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        self.access = resolve_production_access(request.user)
        if not (self.access.can_manage_all or self.access.can_view_planned or self.access.can_edit_planned):
            messages.error(request, "Sem permissão para acessar pesagem de produção.")
            return HttpResponseRedirect(reverse("admin:index"))
        return super().dispatch(request, *args, **kwargs)

    def has_permission(self) -> bool:
        access = getattr(self, "access", None)
        if access is None:
            access = resolve_production_access(self.request.user)
        return access.can_manage_all or access.can_view_planned or access.can_edit_planned

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        selected_date = _dashboard_selected_date(self.request)
        position_ref = (self.request.GET.get("position_ref") or "").strip()
        base_recipe = (self.request.GET.get("base_recipe") or "").strip()
        weighing = build_production_weighing(
            selected_date=selected_date,
            position_ref=position_ref,
            base_recipe=base_recipe,
        )
        filter_form = _weighing_filter_form(weighing)
        context.update({
            "production_weighing": weighing,
            "production_weighing_filter_form": filter_form,
            "production_weighing_filter_fields": _form_fields(filter_form, "date", "position_ref", "base_recipe"),
            "production_flow_tabs": _production_flow_tabs(selected_date, active="planning"),
            "production_weighing_filter_summary": _weighing_filter_summary(weighing),
            "production_weighing_planning_url": _weighing_query_url(
                "admin_console_production_planning",
                weighing,
            ),
            "production_weighing_reset_url": reverse("admin_console_production_weighing"),
        })
        return context


class ProductionCommitmentsView(UnfoldModelAdminViewMixin, TemplateView):
    """Linked order commitments for a work order inside the Admin shell."""

    template_name = COMMITMENTS_TEMPLATE
    title = "Compromissos de produção"
    permission_required: tuple[str, ...] = ()

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        self.access = resolve_production_access(request.user)
        if not self.access.can_access_board:
            messages.error(request, "Sem permissão para acessar produção.")
            return HttpResponseRedirect(reverse("admin:index"))
        try:
            self.work_order, self.order_refs, self.commitments, self.committed_qty = (
                production_service.order_commitments_for_work_order(kwargs["wo_ref"])
            )
        except ObjectDoesNotExist as exc:
            raise Http404("Ordem de produção não encontrada.") from exc
        return super().dispatch(request, *args, **kwargs)

    def has_permission(self) -> bool:
        access = getattr(self, "access", None)
        if access is None:
            access = resolve_production_access(self.request.user)
        return access.can_access_board

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        context.update({
            "production_commitments_work_order": self.work_order,
            "production_commitments_order_refs": self.order_refs,
            "production_commitments_committed_qty": self.committed_qty,
            "production_commitments_table": _commitments_table(self.commitments),
            "production_commitments_back_url": reverse("admin_console_production"),
        })
        return context


def _production_model_admin():
    try:
        return admin.site._registry[WorkOrder]
    except KeyError as exc:
        raise ImproperlyConfigured("WorkOrder must be registered in admin.site for the Production Admin page.") from exc


def production_console_as_view():
    return ProductionConsoleView.as_view(model_admin=_production_model_admin())


def production_console_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    """Resolve the WorkOrder ModelAdmin lazily for URLConf import order."""
    return production_console_as_view()(request, *args, **kwargs)


def production_planning_as_view():
    return ProductionPlanningView.as_view(model_admin=_production_model_admin())


def production_planning_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    """Resolve the WorkOrder ModelAdmin lazily for URLConf import order."""
    return production_planning_as_view()(request, *args, **kwargs)


def production_dashboard_as_view():
    return ProductionDashboardView.as_view(model_admin=_production_model_admin())


def production_dashboard_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    """Resolve the WorkOrder ModelAdmin lazily for URLConf import order."""
    return production_dashboard_as_view()(request, *args, **kwargs)


def production_reports_as_view():
    return ProductionReportsView.as_view(model_admin=_production_model_admin())


def production_reports_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    """Resolve the WorkOrder ModelAdmin lazily for URLConf import order."""
    return production_reports_as_view()(request, *args, **kwargs)


def production_weighing_as_view():
    return ProductionWeighingView.as_view(model_admin=_production_model_admin())


def production_weighing_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    """Resolve the WorkOrder ModelAdmin lazily for URLConf import order."""
    return production_weighing_as_view()(request, *args, **kwargs)


def production_commitments_as_view():
    return ProductionCommitmentsView.as_view(model_admin=_production_model_admin())


def production_commitments_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    """Resolve the WorkOrder ModelAdmin lazily for URLConf import order."""
    return production_commitments_as_view()(request, *args, **kwargs)


def build_production_console_context(request: HttpRequest, board, context: dict) -> dict:
    """Build Unfold component data for the production orders Admin page."""
    filter_form = _filter_form(board)
    production_order_sections = _production_order_sections(
        request,
        board,
        context,
    )
    production_matrix_table = (
        production_order_sections[0]["table"]
        if production_order_sections
        else _empty_table(["", "SKU", "Planejado", "Produzido"])
    )
    return {
        "production_flow_tabs": _production_flow_tabs(board.selected_date, active="production"),
        "production_filter_form": filter_form,
        "production_filter_fields": _form_fields(filter_form, "date", "position_ref", "operator_ref", "base_recipe"),
        "production_quick_finish_form": _quick_finish_form(board),
        "production_reset_url": reverse("admin_console_production"),
        "production_status_tracker": _status_tracker(board),
        "production_matrix_table": production_matrix_table,
        "production_order_sections": production_order_sections,
        "production_filter_summary": _board_filter_summary(board),
        "production_work_orders_today_url": _work_orders_today_url(context["selected_date"]),
    }


def build_production_planning_context(request: HttpRequest, board, context: dict) -> dict:
    """Build Unfold component data for the production planning Admin page."""
    filter_form = _filter_form(board)
    return {
        "production_flow_tabs": _production_flow_tabs(board.selected_date, active="planning"),
        "production_filter_form": filter_form,
        "production_filter_fields": _form_fields(filter_form, "date", "position_ref", "operator_ref", "base_recipe"),
        "production_reset_url": reverse("admin_console_production_planning"),
        "production_filter_summary": _board_filter_summary(board),
        "production_planning_sections": _production_planning_sections(request, board, context),
        "production_matrix_table": _empty_table(["", "SKU", "Recomendado", "Compromisso", "Planejado"]),
        "production_orders_url": _date_query_url("admin_console_production", board.selected_date),
        "production_weighing_url": _production_filter_url("admin_console_production_weighing", board),
        "production_work_orders_today_url": _work_orders_today_url(context["selected_date"]),
    }


def production_console_bulk_create_view(request: HttpRequest) -> HttpResponse:
    """Create suggested work orders from the Admin/Unfold production pages."""
    if request.method != "POST":
        return HttpResponse("Method not allowed", status=405)

    access = resolve_production_access(request.user)
    if not (access.can_manage_all or access.can_edit_planned):
        return HttpResponseForbidden("Você não tem permissão para esta ação.")

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


def _dashboard_selected_date(request: HttpRequest) -> date:
    raw = (request.GET.get("date") or "").strip()
    try:
        return date.fromisoformat(raw) if raw else date.today()
    except ValueError:
        return date.today()


def _position_choices() -> list[tuple[str, str]]:
    from shopman.stockman.models import Position

    return [("", "Todos"), *[(position.ref, position.name) for position in Position.objects.all().order_by("name")]]


def _dashboard_filter_form(*, selected_date: date, position_ref: str) -> ProductionDashboardFilterForm:
    return ProductionDashboardFilterForm(
        initial={
            "date": selected_date,
            "position_ref": position_ref,
        },
        position_choices=_position_choices(),
    )


def _reports_filter_form(reports) -> ProductionReportsFilterForm:
    filters = reports.filters
    return ProductionReportsFilterForm(
        initial={
            "report_kind": filters.report_kind,
            "date_from": filters.date_from,
            "date_to": filters.date_to,
            "recipe_ref": filters.recipe_ref,
            "position_ref": filters.position_ref,
            "operator_ref": filters.operator_ref,
            "status": filters.status,
        },
        recipe_choices=[("", "Todas"), *[(recipe.ref, recipe.name) for recipe in reports.available_recipes]],
        position_choices=[("", "Todos"), *[(position.ref, position.name) for position in reports.available_positions]],
    )


def _weighing_filter_form(weighing) -> ProductionWeighingFilterForm:
    return ProductionWeighingFilterForm(
        initial={
            "date": weighing.selected_date,
            "position_ref": weighing.selected_position_ref,
            "base_recipe": weighing.selected_base_recipe,
        },
        position_choices=_position_choices(),
        base_recipe_choices=_weighing_base_recipe_choices(),
    )


def _form_fields(form: forms.Form, *names: str) -> tuple:
    return tuple(form[name] for name in names)


def _admin_production_links(selected_date) -> tuple[dict, ...]:
    return (
        {
            "label": "Planejamento",
            "href": _date_query_url("admin_console_production_planning", selected_date),
            "icon": "edit_calendar",
            "footer": "Recomendado, compromisso e planejado",
        },
        {
            "label": "Filipetas",
            "href": _date_query_url("admin_console_production_weighing", selected_date),
            "icon": "receipt_long",
            "footer": "Pesagem térmica por ficha-base",
        },
        {
            "label": "Produção",
            "href": _date_query_url("admin_console_production", selected_date),
            "icon": "manufacturing",
            "footer": "Apontamento do dia por SKU",
        },
        {
            "label": "Fichas técnicas",
            "href": reverse("admin:craftsman_recipe_changelist"),
            "icon": "menu_book",
            "footer": "BOM por SKU e insumos",
        },
        {
            "label": "Relatórios",
            "href": _reports_url(selected_date),
            "icon": "table_chart",
            "footer": "Histórico, perdas e rendimento",
        },
    )


def _production_flow_tabs(selected_date, *, active: str) -> tuple[dict, ...]:
    return (
        {
            "title": "Painel",
            "link": _date_query_url("admin_console_production_dashboard", selected_date),
            "active": active == "dashboard",
            "has_permission": True,
        },
        {
            "title": "Planejamento",
            "link": _date_query_url("admin_console_production_planning", selected_date),
            "active": active == "planning",
            "has_permission": True,
        },
        {
            "title": "Produção",
            "link": _date_query_url("admin_console_production", selected_date),
            "active": active == "production",
            "has_permission": True,
        },
        {
            "title": "Fichas técnicas",
            "link": reverse("admin:craftsman_recipe_changelist"),
            "active": active == "recipes",
            "has_permission": True,
        },
        {
            "title": "Relatórios",
            "link": _reports_url(selected_date),
            "active": active == "reports",
            "has_permission": True,
        },
    )


def _dashboard_kpis(dashboard, selected_date: date) -> tuple[dict, ...]:
    date_filter = {
        "target_date_from": selected_date.isoformat(),
        "target_date_to": selected_date.isoformat(),
    }
    return (
        {
            "title": "Planejado",
            "value": _quantity_display(dashboard.planned_qty),
            "footer": _work_order_count_label(dashboard.planned_orders),
            "icon": "event_note",
            "href": _work_order_changelist_url(**date_filter, **{STATUS_FILTER_PARAM: WorkOrder.Status.PLANNED}),
        },
        {
            "title": "Iniciado",
            "value": _quantity_display(dashboard.started_qty),
            "footer": _work_order_count_label(dashboard.started_orders),
            "icon": "timer",
            "href": _work_order_changelist_url(**date_filter, **{STATUS_FILTER_PARAM: WorkOrder.Status.STARTED}),
        },
        {
            "title": "Concluído",
            "value": _quantity_display(dashboard.finished_qty),
            "footer": _work_order_count_label(dashboard.finished_orders),
            "icon": "done_all",
            "href": _work_order_changelist_url(**date_filter, **{STATUS_FILTER_PARAM: WorkOrder.Status.FINISHED}),
        },
        {
            "title": "Rendimento médio",
            "value": dashboard.average_yield_rate or "-",
            "footer": _capacity_footer(dashboard),
            "icon": "analytics",
            "href": _reports_url(selected_date),
        },
    )


def _capacity_footer(dashboard) -> str:
    if dashboard.capacity_percent is None:
        return "Sem capacidade definida"
    return f"Capacidade {dashboard.capacity_percent}%"


def _work_order_count_label(count: int) -> str:
    return f"{count} OP" if count == 1 else f"{count} OPs"


def _quantity_display(value, unit: str = "un.") -> str:
    if value in (None, "", "-"):
        return "-"
    raw = str(value).strip()
    if not raw:
        return "-"
    try:
        normalized = Decimal(raw.replace(",", ".")).quantize(Decimal("0.001")).normalize()
    except (InvalidOperation, ValueError):
        return f"{raw} {unit}"
    return f"{format(normalized, 'f').replace('.', ',')} {unit}"


def _dashboard_late_table(dashboard) -> dict:
    return {
        "headers": ["OP", "Produto", "Tempo (min)", "Meta (min)", "Operador"],
        "rows": [
            [
                item.ref,
                item.output_sku,
                item.elapsed_minutes,
                item.target_minutes,
                item.operator_ref or "-",
            ]
            for item in dashboard.late_orders
        ],
    }


def _reports_title(report_kind: str) -> str:
    return {
        "operator_productivity": "Produtividade por operador",
        "recipe_waste": "Desperdício por ficha técnica",
    }.get(report_kind, "Histórico de ordens")


def _reports_filter_summary(filters) -> str:
    period = f"{filters.date_from.strftime('%d/%m/%Y')} - {filters.date_to.strftime('%d/%m/%Y')}"
    refinements = []
    if filters.recipe_ref:
        refinements.append(filters.recipe_ref)
    if filters.position_ref:
        refinements.append(filters.position_ref)
    if filters.operator_ref:
        refinements.append(filters.operator_ref)
    if filters.status:
        refinements.append(filters.status)
    if not refinements:
        refinements.append("sem refinamentos")
    return f"{period} · {', '.join(refinements)}"


def _weighing_filter_summary(weighing) -> str:
    parts = [weighing.selected_date_display]
    if weighing.selected_position_ref:
        parts.append(weighing.selected_position_ref)
    if weighing.selected_base_recipe:
        parts.append(weighing.selected_base_recipe)
    return " · ".join(parts)


def _reports_filter_reset_url(filters) -> str:
    return _reports_filter_url(
        filters,
        date_from=None,
        date_to=None,
        recipe_ref="",
        position_ref="",
        operator_ref="",
        status="",
    )


def _reports_tabs(filters) -> tuple[dict, ...]:
    return tuple(
        {
            "title": title,
            "link": _reports_filter_url(filters, report_kind=kind),
            "active": filters.report_kind == kind,
            "has_permission": True,
        }
        for kind, title in REPORT_KIND_CHOICES
    )


def _reports_table(reports) -> dict:
    report_kind = reports.filters.report_kind
    if report_kind == "operator_productivity":
        return {
            "headers": ["Operador", "Ordens", "Qtd total", "Rendimento médio", "Tempo médio (min)"],
            "rows": [
                [
                    row.operator_name,
                    row.wo_count,
                    _quantity_display(row.qty_total),
                    row.yield_avg or "-",
                    row.duration_avg_minutes or "-",
                ]
                for row in reports.operator_rows
            ],
        }
    if report_kind == "recipe_waste":
        return {
            "headers": ["Ficha técnica", "Ordens", "Perda total", "Rendimento médio"],
            "rows": [
                [
                    row.recipe_name,
                    row.wo_count,
                    _quantity_display(row.loss_total),
                    row.yield_avg or "-",
                ]
                for row in reports.waste_rows
            ],
        }
    return {
        "headers": [
            "OP",
            "Data agendada",
            "Ficha técnica",
            "Posto",
            "Planejado",
            "Iniciado",
            "Concluído",
            "Perda",
            "Rendimento",
            "Operador",
            "Tempo (min)",
        ],
        "rows": [
            [
                row.ref,
                row.date,
                row.recipe_name,
                row.position_ref or "-",
                _quantity_display(row.qty_planned),
                _quantity_display(row.qty_started),
                _quantity_display(row.qty_finished),
                _quantity_display(row.qty_loss),
                row.yield_rate or "-",
                row.operator_ref or "-",
                row.duration_minutes or "-",
            ]
            for row in reports.history_rows
        ],
    }


def _commitments_table(commitments) -> dict:
    return {
        "headers": ["Pedido", "Status", "Qtd requerida"],
        "rows": [
            [
                f"#{item.ref}",
                item.status,
                item.qty_required,
            ]
            for item in commitments
        ],
    }


def _reports_csv_url(filters) -> str:
    return _reports_filter_url(filters, format="csv")


def _reports_filter_url(filters, **overrides) -> str:
    query = {
        "report_kind": filters.report_kind,
        "date_from": filters.date_from.isoformat(),
        "date_to": filters.date_to.isoformat(),
        "recipe_ref": filters.recipe_ref,
        "position_ref": filters.position_ref,
        "operator_ref": filters.operator_ref,
        "status": filters.status,
    }
    query.update(overrides)
    query = {key: value for key, value in query.items() if value not in (None, "")}
    return f"{reverse('admin_console_production_reports')}?{urlencode(query)}"


def _status_tracker(board) -> tuple[dict, ...]:
    colors = {
        "planned": "bg-blue-500 dark:bg-blue-600",
        "started": "bg-orange-500 dark:bg-orange-600",
        "finished": "bg-green-600 dark:bg-green-700",
        "void": "bg-red-600 dark:bg-red-700",
    }
    return tuple(
        {
            "color": colors.get(item.status, "bg-base-300 dark:bg-base-500"),
            "tooltip": f"{item.ref} - {item.status_label} - {item.output_sku}",
            "href": reverse("admin:craftsman_workorder_change", args=[item.pk]),
        }
        for item in board.work_orders[:80]
    )


def _date_query_url(url_name: str, selected_date) -> str:
    date_value = _date_value(selected_date)
    return f"{reverse(url_name)}?date={date_value}" if date_value else reverse(url_name)


def _reports_url(selected_date) -> str:
    date_value = _date_value(selected_date)
    url = reverse("admin_console_production_reports")
    return f"{url}?date_from={date_value}&date_to={date_value}" if date_value else url


def _weighing_query_url(url_name: str, weighing) -> str:
    query = {
        "date": weighing.selected_date,
        "position_ref": weighing.selected_position_ref,
        "base_recipe": weighing.selected_base_recipe,
    }
    query = {key: value for key, value in query.items() if value not in (None, "")}
    base = reverse(url_name)
    return f"{base}?{urlencode(query)}" if query else base


def _work_order_changelist_url(**params) -> str:
    url = reverse("admin:craftsman_workorder_changelist")
    query = urlencode({key: value for key, value in params.items() if value not in (None, "")})
    return f"{url}?{query}" if query else url


def _work_orders_today_url(selected_date) -> str:
    date_value = _date_value(selected_date)
    if not date_value:
        return reverse("admin:craftsman_workorder_changelist")
    return _work_order_changelist_url(
        target_date_from=date_value,
        target_date_to=date_value,
    )


def _date_value(selected_date) -> str:
    if hasattr(selected_date, "isoformat"):
        return selected_date.isoformat()
    return str(selected_date or "")


def _board_filter_summary(board) -> str:
    parts = [board.selected_date_display]
    if board.selected_position_ref:
        parts.append(board.selected_position_ref)
    if board.selected_operator_ref:
        parts.append(board.selected_operator_ref)
    if board.selected_base_recipe:
        parts.append(board.selected_base_recipe)
    return " · ".join(parts)


def _empty_table(headers: list[str]) -> dict:
    return {
        "collapsible": True,
        "headers": headers,
        "rows": [],
    }


def _production_planning_sections(request: HttpRequest, board, context: dict) -> tuple[dict, ...]:
    sections = []
    for group in board.matrix_groups:
        table = _production_planning_table(request, board, context, group)
        if not table["rows"]:
            continue
        sections.append({
            "title": _group_title(group),
            "subtitle": _group_subtitle(group),
            "table": table,
        })
    return tuple(sections)


def _production_planning_table(request: HttpRequest, board, context: dict, group) -> dict:
    rows = []
    for group_row in group.rows:
        row = group_row.row
        usage = group_row.usage
        rows.append({
            "cols": [
                "",
                _cell(request, "sku", row=row, usage=usage, group=group, context=context),
                _quantity_display(_row_recommended_qty(row)),
                _quantity_display(_row_committed_qty(row)),
                _cell(
                    request,
                    "planning_planned",
                    row=row,
                    context=context,
                    plan_entry=_planning_entry(row, board),
                    adjust_entry=_planning_adjust_entry(row, board),
                ),
            ],
            "table": _details_table(request, row, access=board.access),
        })
    return {
        "collapsible": True,
        "headers": ["", "SKU", "Recomendado", "Compromisso", "Planejado"],
        "rows": rows,
    }


def _production_order_sections(
    request: HttpRequest,
    board,
    context: dict,
) -> tuple[dict, ...]:
    sections = []
    for group in board.matrix_groups:
        table = _production_order_table(request, board, context, group)
        if not table["rows"]:
            continue
        sections.append({
            "title": _group_title(group),
            "subtitle": _group_subtitle(group),
            "table": table,
        })
    return tuple(sections)


def _production_order_table(
    request: HttpRequest,
    board,
    context: dict,
    group,
) -> dict:
    rows = []
    for group_row in group.rows:
        row = group_row.row
        usage = group_row.usage
        rows.append({
            "cols": [
                "",
                _cell(request, "sku", row=row, usage=usage, group=group, context=context),
                _cell(request, "production_planned", row=row),
                _cell(
                    request,
                    "produced",
                    row=row,
                    context=context,
                    entries=_produce_entries(row, board),
                ),
            ],
            "table": _details_table(request, row, access=board.access),
        })
    return {
        "collapsible": True,
        "headers": ["", "SKU", "Planejado", "Produzido"],
        "rows": rows,
    }


def _group_title(group) -> str:
    if group.output_sku:
        return group.name
    return "Fichas diretas"


def _group_subtitle(group) -> str:
    count = len(group.rows)
    sku_label = "SKU" if count == 1 else "SKUs"
    if group.output_sku:
        return f"{group.output_sku} · {count} {sku_label}"
    return f"{count} {sku_label}"


def _row_suggested_qty(row) -> str:
    return _qty_display_value(_decimal_from_display(row.suggestion.quantity if row.suggestion else "0"))


def _row_recommended_qty(row) -> str:
    suggested = _decimal_from_display(_row_suggested_qty(row))
    committed = _decimal_from_display(_row_committed_qty(row))
    return _qty_display_value(max(suggested, committed))


def _row_committed_qty(row) -> str:
    linked_total = Decimal("0")
    for item in (*row.planned_orders, *row.started_orders, *row.finished_orders):
        if getattr(item, "order_commitments", ()):
            linked_total += _decimal_from_display(item.committed_qty)
    suggestion_committed = _decimal_from_display(row.suggestion.committed if row.suggestion else "0")
    return _qty_display_value(max(linked_total, suggestion_committed))


def _decimal_from_display(value) -> Decimal:
    if value in (None, "", "-"):
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _qty_display_value(value: Decimal) -> str:
    if value <= 0:
        return ""
    return format(value.quantize(Decimal("0.001")).normalize(), "f")


def _matrix_table(request: HttpRequest, board, context: dict, *, status: str = "") -> dict:
    sections = _production_order_sections(request, board, context)
    rows = [row for section in sections for row in section["table"]["rows"]]
    return {
        "collapsible": True,
        "headers": ["", "SKU", "Planejado", "Produzido"],
        "rows": rows,
    }


def _details_table(request: HttpRequest, row, *, access) -> dict:
    detail_rows = [
        [
            "Ficha técnica",
            row.output_sku,
            "-",
            "-",
            row.recipe_name,
        ]
    ]

    if row.suggestion and (access.can_view_suggested or access.can_edit_suggested):
        detail_rows.append([
            "Recomendação",
            row.suggestion.recipe_ref,
            _quantity_display(row.suggestion.quantity),
            _quantity_display(row.suggestion.committed),
            f"Média {row.suggestion.avg_demand} - {row.suggestion.confidence}",
        ])

    for usage in row.base_usages:
        detail_rows.append([
            "Ficha-base",
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
                _quantity_display(item.planned_qty),
                _quantity_display(item.committed_qty),
                _commitments(request, item),
            ])
    if access.can_view_started:
        for item in row.started_orders:
            detail_rows.append([
                "Iniciada",
                item.ref,
                _quantity_display(item.started_qty),
                _quantity_display(item.committed_qty),
                item.operator_ref or "-",
            ])
    if access.can_view_finished:
        for item in row.finished_orders:
            detail_rows.append([
                "Concluída",
                item.ref,
                _quantity_display(item.finished_qty),
                _quantity_display(item.committed_qty),
                item.operator_ref or "-",
            ])

    if not detail_rows:
        detail_rows.append(["Sem OP", row.output_sku, "-", "-", "Sem detalhes para os filtros atuais."])

    return {
        "collapsible": True,
        "headers": ["Estado", "OP", "Qtd", "Compromisso", "Detalhe"],
        "rows": detail_rows,
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


def _weighing_base_recipe_choices() -> list[tuple[str, str]]:
    recipes = (
        Recipe.objects.filter(is_active=True)
        .exclude(output_sku="")
        .order_by("name", "output_sku")
        .values_list("output_sku", "name")
    )
    return [("", "Todas"), *[(output_sku, f"{name} ({output_sku})") for output_sku, name in recipes]]


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


def _planning_entry(row, board) -> dict | None:
    if not row.recipe_pk:
        return None
    recommended = _row_recommended_qty(row)
    return {
        "form_id": f"production-plan-{row.recipe_pk}",
        "modal_title": f"Planejar {row.output_sku}",
        "modal_description": "Confirme a quantidade recomendada para a data agendada.",
        "submit_label": "Salvar planejado",
        "form": ProductionPlanForm(
            initial={
                "action": "set_planned",
                "target_date": board.selected_date,
                "position_ref": board.selected_position_ref,
                "operator_ref": board.selected_operator_ref,
                "operator_ref_filter": board.selected_operator_ref,
                "base_recipe": board.selected_base_recipe,
                "recipe": row.recipe_pk,
                "quantity": recommended or row.planned_qty or "0",
            }
        ),
    }


def _planning_adjust_entry(row, board) -> dict | None:
    if not row.recipe_pk or not row.planned_orders:
        return None
    modal_description = "Escolha o motivo e confirme a nova quantidade planejada."
    if len(row.planned_orders) > 1:
        modal_description = (
            "Há mais de um planejamento interno para este SKU. "
            "Salvar consolida tudo em uma única OP planejada."
        )
    return {
        "form_id": f"production-adjust-plan-{row.recipe_pk}",
        "modal_title": f"Ajustar {row.output_sku}",
        "modal_description": modal_description,
        "submit_label": "Salvar ajuste",
        "form": ProductionPlanAdjustForm(
            initial={
                "action": "set_planned",
                "target_date": board.selected_date,
                "position_ref": board.selected_position_ref,
                "operator_ref": board.selected_operator_ref,
                "operator_ref_filter": board.selected_operator_ref,
                "base_recipe": board.selected_base_recipe,
                "recipe": row.recipe_pk,
                "quantity": row.planned_qty,
                "reason": "demand",
            }
        ),
    }


def _produce_entries(row, board) -> list[dict]:
    open_orders = (*row.started_orders, *row.planned_orders)
    if len(open_orders) > 1:
        statuses = ", ".join(f"{item.ref} {item.status_label.lower()}" for item in open_orders)
        return [
            {
                "blocked": True,
                "button_label": f"{len(open_orders)} OPs abertas",
                "button_title": f"{row.output_sku}: {statuses}",
                "resolve_url": _production_filter_url("admin_console_production_planning", board),
            }
        ]

    return [
        {
            "item": item,
            "button_label": _quantity_display(item.started_qty or item.planned_qty),
            "button_title": (
                f"{item.ref} · {item.status_label} · "
                f"{_quantity_display(item.started_qty or item.planned_qty)}"
            ),
            "modal_title": f"Produzir {item.output_sku}",
            "modal_description": "Informe a quantidade realmente produzida para concluir a OP.",
            "submit_label": "Salvar produzido",
            "form_id": f"production-finish-{item.pk}",
            "form": ProductionFinishForm(
                initial={
                    "action": "finish",
                    "wo_id": item.pk,
                    "target_date": board.selected_date,
                    "position_ref": board.selected_position_ref,
                    "operator_ref_filter": board.selected_operator_ref,
                    "base_recipe": board.selected_base_recipe,
                    "quantity": item.started_qty or item.planned_qty,
                }
            ),
        }
        for item in open_orders
    ]


def _production_filter_url(url_name: str, board) -> str:
    query = {
        "date": board.selected_date,
        "position_ref": board.selected_position_ref,
        "operator_ref": board.selected_operator_ref,
        "base_recipe": board.selected_base_recipe,
    }
    query = {key: value for key, value in query.items() if value not in (None, "")}
    base = reverse(url_name)
    return f"{base}?{urlencode(query)}" if query else base


def _position_pk_choices(board) -> list[tuple[str | int, str]]:
    return [("", "Padrão"), *[(position.pk, position.name) for position in board.positions]]


def _commitments(request: HttpRequest, item):
    if not item.order_commitments:
        return "-"
    return mark_safe(
        render_to_string(
            "admin_console/production/cells/commitments.html",
            {"item": item, "committed_qty": _quantity_display(item.committed_qty)},
            request=request,
        )
    )


def _cell(request: HttpRequest, name: str, **context):
    return mark_safe(
        render_to_string(
            f"admin_console/production/cells/{name}.html",
            context,
            request=request,
        )
    )
