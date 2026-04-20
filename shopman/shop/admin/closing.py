"""DayClosing admin — readonly day-closing records."""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin

from shopman.backstage.models import DayClosing


@admin.register(DayClosing)
class DayClosingAdmin(ModelAdmin):
    list_display = ("date", "closed_by", "closed_at")
    list_filter = ("date",)
    readonly_fields = ("date", "closed_by", "closed_at", "notes", "data")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("shop.perform_closing")
