"""KDSInstance admin — kitchen display station configuration."""

from __future__ import annotations

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.backstage.models import KDSInstance
from shopman.utils import unfold_badge


@admin.register(KDSInstance)
class KDSInstanceAdmin(ModelAdmin):
    list_display = ["name", "ref", "type_badge", "target_time_minutes", "sound_enabled", "is_active_badge", "open_display"]
    list_filter = ["type", "is_active"]
    search_fields = ["name", "ref"]
    prepopulated_fields = {"ref": ("name",)}
    filter_horizontal = ["collections"]
    compressed_fields = True
    warn_unsaved_form = True
    fieldsets = [
        (None, {"fields": ("name", "ref", "type")}),
        ("Coleções", {
            "fields": ("collections",),
            "description": "Categorias de produto que esta estação processa. Vazio = catch-all.",
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
        return format_html(
            '<a class="font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400" href="{}">Abrir</a>',
            reverse("backstage:kds_display", args=[obj.ref]),
        )

    def has_add_permission(self, request):
        return request.user.has_perm("backstage.operate_kds")

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("backstage.operate_kds")

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm("backstage.operate_kds")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("backstage.operate_kds")
