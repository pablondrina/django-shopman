"""Catálogo de copy omotenashi — página Admin canônica (Unfold).

Inverte o índice do changelist: TODAS as chaves registradas, agrupadas por
superfície → tela (mapa chave↔tela derivado do código), com default, estado de
override e link direto para personalizar. É a resposta ao "eu mudaria no admin,
se eu soubesse onde" — o operador navega pela TELA que está vendo, não pela
chave que não conhece.
"""

from __future__ import annotations

from django import forms
from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.utils.html import format_html
from django.views.generic import TemplateView
from shopman.utils import table_badge
from unfold.views import UnfoldModelAdminViewMixin
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextInputWidget

from shopman.backstage.projections.copy_catalog import (
    build_copy_catalog,
)


class CopyCatalogFilterForm(forms.Form):
    q = forms.CharField(
        label="Buscar",
        required=False,
        widget=UnfoldAdminTextInputWidget(
            attrs={"placeholder": "Chave ou texto que aparece na tela"}
        ),
    )
    surface = forms.ChoiceField(
        label="Superfície",
        required=False,
        widget=UnfoldAdminSelectWidget,
        choices=(("", "Todas"),),
    )

    def __init__(self, *args, surfaces: tuple[str, ...] = (), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["surface"].choices = [("", "Todas"), *[(s, s) for s in surfaces]]


class CopyCatalogView(UnfoldModelAdminViewMixin, TemplateView):
    title = "Catálogo de copy"
    permission_required = "shop.view_omotenashicopy"
    template_name = "admin_console/copy_catalog/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        q = self.request.GET.get("q", "")
        surface = self.request.GET.get("surface", "")
        catalog = build_copy_catalog(q=q, surface=surface)
        form = CopyCatalogFilterForm(
            self.request.GET or None, surfaces=catalog.surfaces
        )
        context.update(
            {
                "copy_catalog": catalog,
                "copy_catalog_form": form,
                "copy_catalog_tables": [
                    {
                        "surface": group.surface,
                        "screen": group.screen,
                        "count": len(group.rows),
                        "table": _group_table(group.rows),
                    }
                    for group in catalog.groups
                ],
            }
        )
        return context


def _group_table(rows) -> dict:
    built = []
    for row in rows:
        default_display = row.default_title or "—"
        if row.default_message:
            message = row.default_message
            if len(message) > 80:
                message = f"{message[:77]}…"
            default_display = format_html(
                '{}<span class="block text-xs text-base-500">{}</span>',
                default_display,
                message,
            )
        state = (
            table_badge(f"{row.override_count} personalizada(s)", "orange")
            if row.override_count
            else table_badge("Padrão do código", "base")
        )
        actions = format_html(
            '<a href="{}" class="font-medium underline underline-offset-4">Personalizar</a>',
            row.add_url,
        )
        if row.override_count:
            actions = format_html(
                '{} · <a href="{}" class="font-medium underline underline-offset-4">Ver ajustes</a>',
                actions,
                row.list_url,
            )
        built.append([
            format_html('<span class="font-medium">{}</span>', row.key),
            default_display,
            row.variant_count,
            state,
            row.other_screens or "—",
            actions,
        ])
    return {
        "headers": ["Chave", "Texto padrão", "Variações", "Estado", "Também em", "Ações"],
        "rows": built,
    }


def _copy_model_admin():
    from shopman.shop.models import OmotenashiCopy

    return admin.site._registry[OmotenashiCopy]


def copy_catalog_as_view():
    return CopyCatalogView.as_view(model_admin=_copy_model_admin())


def copy_catalog_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    """Resolve o ModelAdmin de OmotenashiCopy tardiamente (ordem de import do URLConf)."""
    return copy_catalog_as_view()(request, *args, **kwargs)
