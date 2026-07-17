"""ShowcaseAdmin — Expositor: exibe coleções curadas num alvo (menuboard/feed)."""

from __future__ import annotations

import logging

from django import forms
from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import display
from unfold.widgets import UnfoldAdminSelectMultipleWidget

from shopman.shop.models import Showcase

logger = logging.getLogger(__name__)


class ShowcaseForm(forms.ModelForm):
    """As coleções (seções/segmentos) via multi-seleção das coleções ativas."""

    collections = forms.MultipleChoiceField(
        required=False,
        widget=UnfoldAdminSelectMultipleWidget,
        help_text=(
            "Coleções que compõem o expositor — no menuboard viram as seções; no feed, "
            "os segmentos (custom_label). A ordem segue a ordenação das coleções."
        ),
    )

    class Meta:
        model = Showcase
        fields = ("ref", "name", "kind", "collections", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["collections"].choices = self._collection_choices()
        if self.instance and self.instance.pk:
            self.fields["collections"].initial = self.instance.collection_refs()

    @staticmethod
    def _collection_choices():
        try:
            from shopman.offerman.models import Collection

            return [
                (c.ref, f"{c.name} ({c.ref})")
                for c in Collection.objects.filter(is_active=True).order_by("sort_order", "name")
            ]
        except Exception:
            logger.debug("showcase_form.collection_choices_failed", exc_info=True)
            return []


@admin.register(Showcase)
class ShowcaseAdmin(ModelAdmin):
    form = ShowcaseForm
    list_display = ("ref", "name", "kind_badge", "collections_count", "is_active")
    list_filter = ("kind", "is_active")
    search_fields = ("ref", "name")
    ordering = ("name",)
    prepopulated_fields = {"ref": ("name",)}
    fieldsets = (
        (None, {
            "fields": ("ref", "name", "kind", "collections", "is_active"),
            "description": (
                "Um Expositor MOSTRA coleções para fora, sem vender: 📺 menuboard (TV) ou "
                "🛰 feed (Google/Meta). Escolha o tipo e as coleções — os links abaixo apontam "
                "a superfície pronta."
            ),
        }),
        ("Superfície pronta", {"fields": ("surface_links",)}),
    )
    readonly_fields = ("surface_links",)

    _KIND_BADGE = {
        Showcase.KIND_MENUBOARD: "Menuboard",
        Showcase.KIND_GOOGLE: "Feed Google",
        Showcase.KIND_META: "Feed Meta",
    }

    @display(
        description="Tipo",
        label={"Menuboard": "info", "Feed Google": "success", "Feed Meta": "warning"},
    )
    def kind_badge(self, obj):
        return self._KIND_BADGE.get(obj.kind, obj.kind)

    @admin.display(description="Coleções")
    def collections_count(self, obj):
        return len(obj.collection_refs())

    @admin.display(description="Superfície pronta")
    def surface_links(self, obj):
        if not obj or not obj.pk:
            return "Salve o expositor para ver os links."
        if obj.kind == Showcase.KIND_MENUBOARD:
            return format_html(
                'Menuboard: <a class="text-primary-600 underline" href="/menuboard/{}/" '
                'target="_blank">/menuboard/{}/</a>',
                obj.ref, obj.ref,
            )
        platform = "meta" if obj.kind == Showcase.KIND_META else "google"
        suffix = "?platform=meta" if obj.kind == Showcase.KIND_META else ""
        return format_html(
            'Feed ({}): <a class="text-primary-600 underline" href="/feed/{}.xml{}" '
            'target="_blank">/feed/{}.xml{}</a>',
            platform, obj.ref, suffix, obj.ref, suffix,
        )
