"""POS tab admin."""

from __future__ import annotations

from django.contrib import admin
from shopman.orderman.models import Session
from shopman.utils import unfold_badge
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.backstage.models import POSTab


@admin.register(POSTab)
class POSTabAdmin(ModelAdmin):
    list_display = ("code", "display_code", "label", "state_display", "is_active_display")
    list_filter = ("is_active",)
    search_fields = ("code", "label")
    ordering = ("code",)
    compressed_fields = True
    list_fullwidth = True

    @display(description="atalho")
    def display_code(self, obj):
        return obj.display_code

    @display(description="estado")
    def state_display(self, obj):
        in_use = Session.objects.filter(
            channel_ref="pdv",
            state="open",
            handle_type="pos_tab",
            handle_ref=obj.code,
        ).exists()
        return unfold_badge("em uso" if in_use else "vazia", "yellow" if in_use else "base")

    @display(description="ativa")
    def is_active_display(self, obj):
        return unfold_badge("ativa" if obj.is_active else "inativa", "green" if obj.is_active else "base")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("backstage.operate_pos")

    def has_add_permission(self, request):
        return request.user.has_perm("backstage.operate_pos")

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("backstage.operate_pos")

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm("backstage.operate_pos")
