"""KDSInstance admin — kitchen display station configuration."""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin

from shopman.shop.models import KDSInstance


@admin.register(KDSInstance)
class KDSInstanceAdmin(ModelAdmin):
    list_display = ["name", "ref", "type", "target_time_minutes", "sound_enabled", "is_active"]
    list_filter = ["type", "is_active"]
    search_fields = ["name", "ref"]
    prepopulated_fields = {"ref": ("name",)}
    filter_horizontal = ["collections"]
    fieldsets = [
        (None, {"fields": ("name", "ref", "type")}),
        ("Coleções", {
            "fields": ("collections",),
            "description": "Categorias de produto que esta estação processa. Vazio = catch-all.",
        }),
        ("Configuração", {"fields": ("target_time_minutes", "sound_enabled", "is_active", "config")}),
    ]

    def has_add_permission(self, request):
        return request.user.has_perm("shop.operate_kds")

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("shop.operate_kds")

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm("shop.operate_kds")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("shop.operate_kds")
