"""Delivery admin — faixas de distância (motor) + zonas CEP/bairro (exceção)."""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin

from shopman.storefront.models import DeliveryDistanceBand, DeliveryZone


@admin.register(DeliveryDistanceBand)
class DeliveryDistanceBandAdmin(ModelAdmin):
    list_display = ("max_distance_km", "fee_display", "sort_order", "is_active")
    list_filter = ("is_active", "shop")
    ordering = ("max_distance_km", "sort_order")
    list_editable = ("sort_order", "is_active")

    @admin.display(description="taxa")
    def fee_display(self, obj):
        if obj.fee_q == 0:
            return "grátis"
        return f"R$ {obj.fee_q / 100:.2f}".replace(".", ",")


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(ModelAdmin):
    list_display = ("name", "mode", "zone_type", "match_value", "fee_display", "sort_order", "is_active")
    list_filter = ("mode", "zone_type", "is_active", "shop")
    search_fields = ("name", "match_value")
    ordering = ("zone_type", "sort_order", "name")
    list_editable = ("sort_order", "is_active")

    @admin.display(description="taxa")
    def fee_display(self, obj):
        if obj.mode == DeliveryZone.MODE_EXCLUDE:
            return "—"
        if obj.fee_q == 0:
            return "grátis"
        return f"R$ {obj.fee_q / 100:.2f}".replace(".", ",")
