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
    fieldsets = (
        (None, {
            "fields": ("shop", "max_distance_km", "fee_q", "sort_order", "is_active"),
            "description": (
                "Motor da entrega: a taxa é a primeira faixa cuja distância "
                "(loja → endereço) cobre o pedido. Endereços além da maior faixa "
                "ficam fora da área. Exceções por bairro/CEP ficam em "
                "“Zonas de entrega”."
            ),
        }),
    )

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
    fieldsets = (
        (None, {
            "fields": ("shop", "name", "zone_type", "match_value", "mode", "fee_q", "sort_order", "is_active"),
            "description": (
                "Exceções à taxa por distância. “Sobrepor taxa” fixa um valor para "
                "um bairro/CEP (0 = grátis); “Não entregar” bloqueia o checkout "
                "naquela região. Prefixo de CEP tem prioridade sobre bairro."
            ),
        }),
    )

    @admin.display(description="taxa")
    def fee_display(self, obj):
        if obj.mode == DeliveryZone.MODE_EXCLUDE:
            return "—"
        if obj.fee_q == 0:
            return "grátis"
        return f"R$ {obj.fee_q / 100:.2f}".replace(".", ",")
