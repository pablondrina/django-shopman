"""Admin/Unfold day closing console."""

from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse
from django.views.generic import TemplateView
from unfold.views import UnfoldModelAdminViewMixin
from unfold.widgets import UnfoldAdminIntegerFieldWidget

from shopman.backstage.models import DayClosing
from shopman.backstage.projections.closing import build_day_closing
from shopman.backstage.services.closing import perform_day_closing

TEMPLATE = "admin_console/closing/index.html"
PERMISSION = "backstage.perform_closing"


class DayClosingForm(forms.Form):
    def __init__(self, *args, items=(), disabled: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        for item in items:
            self.fields[f"qty_{item.sku}"] = forms.IntegerField(
                label=f"Sobraram de {item.name}",
                min_value=0,
                initial=0,
                disabled=disabled,
                widget=UnfoldAdminIntegerFieldWidget(
                    attrs={"class": "max-w-none", "min": "0", "inputmode": "numeric"}
                ),
            )


class DayClosingConsoleView(UnfoldModelAdminViewMixin, TemplateView):
    """Blind day closing form rendered through the Admin/Unfold shell."""

    template_name = TEMPLATE
    title = "Fechamento"
    permission_required: tuple[str, ...] = ()

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not _can_close_day(request.user):
            return HttpResponseForbidden("Voce nao tem permissao para fechamento do dia.")
        return super().dispatch(request, *args, **kwargs)

    def has_permission(self) -> bool:
        return _can_close_day(self.request.user)

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        closing = build_day_closing()
        form = DayClosingForm(request.POST, items=closing.items, disabled=closing.already_closed)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(closing=closing, form=form))
        try:
            closing_date = perform_day_closing(
                user=request.user,
                items=closing.items,
                quantities_by_sku={
                    item.sku: form.cleaned_data.get(f"qty_{item.sku}", 0)
                    for item in closing.items
                },
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect(reverse("admin_console_day_closing"))
        messages.success(request, f"Fechamento do dia {closing_date} realizado com sucesso.")
        return HttpResponseRedirect(reverse("admin_console_day_closing"))

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        closing = kwargs.get("closing") or build_day_closing()
        form = kwargs.get("form") or DayClosingForm(items=closing.items, disabled=closing.already_closed)
        context.update({
            "day_closing": closing,
            "day_closing_form": form,
            "day_closing_items_table": _items_table(closing, form),
            "day_closing_production_table": _production_table(closing),
            "day_closing_reconciliation_table": _reconciliation_table(closing),
            "day_closing_reports_url": _reports_url(closing),
        })
        return context


def _closing_model_admin():
    try:
        return admin.site._registry[DayClosing]
    except KeyError as exc:
        raise ImproperlyConfigured("DayClosing must be registered in admin.site for the Closing Admin page.") from exc


def day_closing_console_as_view():
    return DayClosingConsoleView.as_view(model_admin=_closing_model_admin())


def day_closing_console_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    return day_closing_console_as_view()(request, *args, **kwargs)


def _items_table(closing, form: DayClosingForm) -> dict:
    return {
        "headers": ["SKU", "Produto", "Sobraram"],
        "rows": [
            [
                item.sku,
                item.name,
                form[f"qty_{item.sku}"],
            ]
            for item in closing.items
        ],
    }


def _production_table(closing) -> dict:
    rows = []
    for recipe_ref, row in closing.production_summary.items():
        rows.append([
            row.get("output_sku") or recipe_ref,
            row.get("planned", 0),
            row.get("finished", 0),
            row.get("loss", 0),
        ])
    return {
        "headers": ["SKU", "Planejado", "Feito", "Perda"],
        "rows": rows,
    }


def _reconciliation_table(closing) -> dict:
    return {
        "headers": ["SKU", "Vendido", "Disponivel", "Deficit"],
        "rows": [
            [error.sku, error.sold_qty, error.available_qty, error.deficit_qty]
            for error in closing.reconciliation_errors
        ],
    }


def _reports_url(closing) -> str:
    return (
        f"{reverse('admin_console_production_reports')}"
        f"?date_from={closing.today}&date_to={closing.today}&report_kind=history&format=csv"
    )


def _can_close_day(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or user.has_perm(PERMISSION))
