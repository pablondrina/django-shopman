"""DeliveryZone admin — zonas de entrega por loja."""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin

from shopman.storefront.models import DeliveryZone


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(ModelAdmin):
    list_display = ("name", "zone_type", "match_value", "fee_display", "sort_order", "is_active")
    list_filter = ("zone_type", "is_active", "shop")
    search_fields = ("name", "match_value")
    ordering = ("zone_type", "sort_order", "name")
    list_editable = ("sort_order", "is_active")

    @admin.display(description="taxa")
    def fee_display(self, obj):
        if obj.fee_q == 0:
            return "grátis"
        return f"R$ {obj.fee_q / 100:.2f}".replace(".", ",")
