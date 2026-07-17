"""KDSInstance admin — kitchen display station configuration."""

from __future__ import annotations

from django.conf import settings
from django.contrib import admin
from django.utils.html import format_html
from shopman.utils import unfold_badge
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.backstage.models import KDSInstance


@admin.register(KDSInstance)
class KDSInstanceAdmin(ModelAdmin):
    list_display = ["name", "ref", "type_badge", "target_time_minutes", "sound_enabled", "is_active_badge", "open_display"]
    list_filter = ["type", "is_active"]
    search_fields = ["name", "ref"]
    ordering = ["name"]
    prepopulated_fields = {"ref": ("name",)}
    filter_horizontal = ["collections"]
    compressed_fields = True
    warn_unsaved_form = True
    fieldsets = [
        (None, {"fields": ("name", "ref", "type")}),
        ("Coleções", {
            "fields": ("collections",),
            "description": "Categorias de produto que esta estação processa. Vazio = processa todas as categorias.",
        }),
        ("Configuração", {"fields": ("target_time_minutes", "sound_enabled", "is_active", "config")}),
    ]

    @display(description="tipo")
    def type_badge(self, obj):
        colors = {"prep": "yellow", "picking": "blue", "expedition": "green"}
        return unfold_badge(obj.get_type_display(), colors.get(obj.type, "base"))

    @display(description="ativa")
    def is_active_badge(self, obj):
        if obj.is_active:
            return unfold_badge("ativa", "green")
        return unfold_badge("inativa", "base")

    @display(description="operação")
    def open_display(self, obj):
        # KDS é app Nuxt dedicado (kds.) — sem rota Django. Link só quando a base
        # URL do deployment está configurada (estação fica em /<ref>).
        base = (getattr(settings, "SHOPMAN_KDS_BASE_URL", "") or "").rstrip("/")
        if not base:
            return "—"
        return format_html(
            '<a class="font-medium text-link" href="{}/{}">Abrir</a>',
            base,
            obj.ref,
        )

    def has_add_permission(self, request):
        return request.user.has_perm("backstage.operate_kds")

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("backstage.operate_kds")

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm("backstage.operate_kds")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("backstage.operate_kds")
