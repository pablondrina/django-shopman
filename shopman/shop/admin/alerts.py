"""OperatorAlert admin — readonly alerts with acknowledge action."""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin

from shopman.shop.models import OperatorAlert


@admin.register(OperatorAlert)
class OperatorAlertAdmin(ModelAdmin):
    list_display = ("type", "severity", "short_message", "order_ref", "acknowledged", "created_at")
    list_filter = ("type", "severity", "acknowledged")
    search_fields = ("message", "order_ref")
    readonly_fields = ("type", "severity", "message", "order_ref", "created_at")
    list_per_page = 50
    ordering = ("-created_at",)
    actions = ["mark_acknowledged"]

    @admin.display(description="mensagem")
    def short_message(self, obj):
        return obj.message[:80] + "\u2026" if len(obj.message) > 80 else obj.message

    @admin.action(description="Marcar como reconhecido")
    def mark_acknowledged(self, request, queryset):
        updated = queryset.filter(acknowledged=False).update(acknowledged=True)
        self.message_user(request, f"{updated} alerta(s) reconhecido(s).")
