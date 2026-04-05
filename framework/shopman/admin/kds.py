"""KDSInstance admin — kitchen display station configuration."""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin

from shopman.models import KDSInstance


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
