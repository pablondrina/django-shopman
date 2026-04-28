"""DayClosing admin — readonly day-closing records."""

from __future__ import annotations

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.backstage.models import DayClosing
from shopman.utils import unfold_badge_numeric


@admin.register(DayClosing)
class DayClosingAdmin(ModelAdmin):
    list_display = ("date", "closed_by", "closed_at", "items_count_display", "errors_count_display", "operation_link_display")
    list_filter = ("date",)
    readonly_fields = ("date", "closed_by", "closed_at", "notes", "data")
    compressed_fields = True
    list_fullwidth = True

    @display(description="itens")
    def items_count_display(self, obj):
        data = obj.data if isinstance(obj.data, dict) else {"items": obj.data or []}
        return unfold_badge_numeric(str(len(data.get("items") or [])), "base")

    @display(description="discrepâncias")
    def errors_count_display(self, obj):
        data = obj.data if isinstance(obj.data, dict) else {}
        count = len(data.get("reconciliation_errors") or [])
        return unfold_badge_numeric(str(count), "red" if count else "green")

    @display(description="operação")
    def operation_link_display(self, obj):
        url = f'{reverse("backstage:production_reports")}?date_from={obj.date.isoformat()}&date_to={obj.date.isoformat()}'
        return format_html(
            '<a class="font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400" href="{}">Relatório</a>',
            url,
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("backstage.perform_closing")
