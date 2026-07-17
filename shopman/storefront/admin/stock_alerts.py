"""Aviso de reposição admin — a fila "Me avise quando disponível".

Read-only operator surface: quem está esperando um SKU esgotado voltar. O
disparo é automático (receiver de chegada de estoque, idempotente via
``notified_at``); o operador só consulta a fila, filtra pelos pendentes e limpa
o que já não interessa.
"""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.storefront.models import StockAlertSubscription


class PendingAlertFilter(admin.SimpleListFilter):
    title = "situação"
    parameter_name = "situacao"

    def lookups(self, request, model_admin):
        return [("pendente", "Aguardando"), ("avisado", "Avisado")]

    def queryset(self, request, queryset):
        if self.value() == "pendente":
            return queryset.filter(notified_at__isnull=True)
        if self.value() == "avisado":
            return queryset.filter(notified_at__isnull=False)
        return queryset


@admin.register(StockAlertSubscription)
class StockAlertSubscriptionAdmin(ModelAdmin):
    list_display = ("sku", "who_display", "channel_ref", "status_badge", "subscribed_at")
    list_filter = (PendingAlertFilter, "channel_ref")
    search_fields = ("sku", "customer_ref", "contact_phone")
    ordering = ("-subscribed_at",)
    date_hierarchy = "subscribed_at"
    readonly_fields = ("sku", "channel_ref", "customer_ref", "contact_phone", "subscribed_at", "notified_at")
    list_fullwidth = True
    compressed_fields = True

    @admin.display(description="quem espera")
    def who_display(self, obj):
        return obj.customer_ref or obj.contact_phone or "—"

    @display(description="situação", label={"Aguardando": "warning", "Avisado": "success"})
    def status_badge(self, obj):
        return "Aguardando" if obj.is_pending else "Avisado"

    def has_add_permission(self, request):
        # A fila é populada pela loja (cliente pede "me avise"); nunca à mão.
        return False

    def has_change_permission(self, request, obj=None):
        return False
