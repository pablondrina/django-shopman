"""OperatorAlert admin — trilha readonly de alertas.

O reconhecimento operacional vive no Gestor (AlertsBell →
POST /api/v1/backstage/alerts/<pk>/ack/); o Admin só consulta a trilha.
"""

from __future__ import annotations

from django.contrib import admin
from shopman.utils import unfold_badge
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.backstage.models import OperatorAlert


@admin.register(OperatorAlert)
class OperatorAlertAdmin(ModelAdmin):
    list_display = (
        "type",
        "severity",
        "severity_badge",
        "short_message",
        "order_ref",
        "acknowledged",
        "acknowledged_badge",
        "created_at",
    )
    list_filter = ("type", "severity", "acknowledged")
    search_fields = ("message", "order_ref")
    readonly_fields = ("type", "severity", "message", "order_ref", "created_at")
    list_per_page = 50
    ordering = ("-created_at",)
    list_fullwidth = True
    compressed_fields = True

    @display(description="severidade")
    def severity_badge(self, obj):
        colors = {"warning": "yellow", "error": "red", "critical": "red"}
        return unfold_badge(obj.get_severity_display(), colors.get(obj.severity, "base"))

    @display(description="reconhecido")
    def acknowledged_badge(self, obj):
        if obj.acknowledged:
            return unfold_badge("sim", "green")
        return unfold_badge("pendente", "yellow")

    @display(description="mensagem")
    def short_message(self, obj):
        return obj.message[:80] + "…" if len(obj.message) > 80 else obj.message
