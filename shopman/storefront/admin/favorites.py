"""Favoritos admin — leitura da "coleção dinâmica do cliente".

Superfície de consulta: quais SKUs os clientes mais favoritam (sinal de
interesse para vitrine/produção). Escrito pela loja (coração no card/PDP); o
operador só consulta.
"""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin

from shopman.storefront.models import CustomerFavorite


@admin.register(CustomerFavorite)
class CustomerFavoriteAdmin(ModelAdmin):
    list_display = ("sku", "customer_ref", "created_at")
    list_filter = ("sku",)
    search_fields = ("sku", "customer_ref")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    readonly_fields = ("customer_ref", "sku", "created_at")
    list_fullwidth = True
    compressed_fields = True

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
