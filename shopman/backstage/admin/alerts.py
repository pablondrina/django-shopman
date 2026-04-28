"""OperatorAlert admin — readonly alerts with acknowledge action."""

from __future__ import annotations

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from unfold.admin import ModelAdmin
from unfold.decorators import action, display
from unfold.enums import ActionVariant

from shopman.backstage.models import OperatorAlert
from shopman.utils import unfold_badge


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
    actions = ["mark_acknowledged"]
    actions_row = ["acknowledge_row"]
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
        return obj.message[:80] + "\u2026" if len(obj.message) > 80 else obj.message

    @admin.action(description="Marcar como reconhecido")
    def mark_acknowledged(self, request, queryset):
        updated = queryset.filter(acknowledged=False).update(acknowledged=True)
        self.message_user(request, f"{updated} alerta(s) reconhecido(s).")

    @action(
        description="Reconhecer",
        url_path="ack-alert",
        icon="done",
        variant=ActionVariant.SUCCESS,
    )
    def acknowledge_row(self, request, object_id):
        alert = self.get_object(request, object_id)
        if alert is None:
            messages.error(request, "Alerta não encontrado.")
        elif alert.acknowledged:
            messages.info(request, "Alerta já estava reconhecido.")
        else:
            alert.acknowledged = True
            alert.save(update_fields=["acknowledged"])
            messages.success(request, "Alerta reconhecido.")
        return HttpResponseRedirect(reverse("admin:backstage_operatoralert_changelist"))
