"""Delivery admin — faixas de distância (motor) + zonas CEP/bairro (exceção)."""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.storefront.models import DeliveryDistanceBand, DeliveryZone


@admin.register(DeliveryDistanceBand)
class DeliveryDistanceBandAdmin(ModelAdmin):
    # Lista arrastável (Unfold) em vez da coluna numérica de ordem. O motor
    # avalia pela distância (a menor faixa que cobre o pedido vence); o arraste
    # define a ordem de exibição/empate.
    ordering_field = "sort_order"
    hide_ordering_field = True
    list_display = ("max_distance_km", "fee_display", "is_active")
    list_filter = ("is_active", "shop")
    ordering = ("sort_order", "max_distance_km")
    list_editable = ("is_active",)
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
    # Prioridade manual → lista arrastável (Unfold ordering_field) em vez de
    # uma coluna numérica de ordem. Menor sort_order = maior prioridade.
    ordering_field = "sort_order"
    hide_ordering_field = True
    list_display = ("name", "mode_badge", "zone_type_badge", "match_value", "fee_display", "is_active")
    list_filter = ("mode", "zone_type", "is_active", "shop")
    search_fields = ("name", "match_value")
    ordering = ("sort_order", "name")
    list_editable = ("is_active",)

    @display(
        description="Modo",
        label={"Sobrepor taxa (fixa)": "info", "Não entregar (bloquear)": "danger"},
    )
    def mode_badge(self, obj):
        return obj.get_mode_display()

    @display(
        description="Tipo",
        label={"Prefixo de CEP": "info", "Bairro": "warning"},
    )
    def zone_type_badge(self, obj):
        return obj.get_zone_type_display()

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
