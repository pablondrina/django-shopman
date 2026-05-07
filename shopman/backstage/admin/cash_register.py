"""Admin for CashRegisterSession + CashMovement."""

from __future__ import annotations

from django.contrib import admin
from shopman.utils import unfold_badge, unfold_badge_numeric
from shopman.utils.monetary import format_money
from unfold.admin import ModelAdmin

from shopman.backstage.models import CashMovement, CashRegisterSession


class CashMovementInline(admin.TabularInline):
    model = CashMovement
    extra = 0
    readonly_fields = ("movement_type", "amount_display", "reason", "created_by", "created_at")
    fields = ("movement_type", "amount_display", "reason", "created_by", "created_at")

    def amount_display(self, obj):
        return f"R$ {format_money(obj.amount_q)}"
    amount_display.short_description = "Valor"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CashRegisterSession)
class CashRegisterSessionAdmin(ModelAdmin):
    list_display = ("operator", "opened_at", "status_display", "opening_display", "closing_display", "difference_display")
    list_filter = ("status", "opened_at")
    readonly_fields = (
        "operator", "opened_at", "closed_at", "status",
        "opening_display", "closing_display", "expected_display", "difference_display",
        "notes",
    )
    inlines = [CashMovementInline]
    ordering = ["-opened_at"]
    list_fullwidth = True
    compressed_fields = True

    def status_display(self, obj):
        if obj.status == CashRegisterSession.Status.OPEN:
            return unfold_badge("aberto", "yellow")
        return unfold_badge("fechado", "green")
    status_display.short_description = "Status"

    def opening_display(self, obj):
        return unfold_badge_numeric(f"R$ {format_money(obj.opening_amount_q)}", "base")
    opening_display.short_description = "Abertura"

    def closing_display(self, obj):
        if obj.closing_amount_q is None:
            return "—"
        return unfold_badge_numeric(f"R$ {format_money(obj.closing_amount_q)}", "base")
    closing_display.short_description = "Fechamento"

    def expected_display(self, obj):
        if obj.expected_amount_q is None:
            return "—"
        return f"R$ {format_money(obj.expected_amount_q)}"
    expected_display.short_description = "Esperado"

    def difference_display(self, obj):
        if obj.difference_q is None:
            return "—"
        sign = "+" if obj.difference_q >= 0 else ""
        color = "green" if obj.difference_q == 0 else "yellow"
        return unfold_badge_numeric(f"{sign}R$ {format_money(obj.difference_q)}", color)
    difference_display.short_description = "Diferença"

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("backstage.operate_pos")
