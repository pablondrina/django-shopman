"""Admin for RuleConfig — configurable rules via Unfold."""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin

from shopman.shop.models import RuleConfig


class RuleTypeFilter(admin.SimpleListFilter):
    """Filter rules by type (modifier/validator) based on rule_path."""

    title = "tipo"
    parameter_name = "rule_type"

    def lookups(self, request, model_admin):
        return [
            ("modifier", "Modifier (pricing)"),
            ("validator", "Validator"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "modifier":
            return queryset.filter(rule_path__contains=".pricing.")
        if self.value() == "validator":
            return queryset.filter(rule_path__contains=".validation.")
        return queryset


@admin.register(RuleConfig)
class RuleConfigAdmin(ModelAdmin):
    list_display = ("label", "code", "enabled", "priority", "rule_type_display")
    list_filter = ("enabled", RuleTypeFilter)
    search_fields = ("label", "code")
    list_editable = ("enabled",)
    ordering = ("priority",)
    filter_horizontal = ("channels",)
    fieldsets = [
        (None, {"fields": ("code", "label", "rule_path", "enabled", "priority")}),
        ("Parâmetros", {
            "fields": ("params",),
            "description": "Parâmetros JSON da regra (ex: percentual, horários, valor mínimo).",
        }),
        ("Canais", {
            "fields": ("channels",),
            "description": "Canais onde esta regra se aplica. Vazio = todos os canais.",
        }),
    ]
    actions = ["enable_rules", "disable_rules"]

    def has_add_permission(self, request):
        return request.user.has_perm("shop.manage_rules")

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("shop.manage_rules")

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm("shop.manage_rules")

    @admin.display(description="tipo")
    def rule_type_display(self, obj):
        if ".pricing." in obj.rule_path:
            return "Modifier"
        if ".validation." in obj.rule_path:
            return "Validator"
        return "—"

    @admin.action(description="Ativar regras selecionadas")
    def enable_rules(self, request, queryset):
        updated = queryset.update(enabled=True)
        self.message_user(request, f"{updated} regra(s) ativada(s).")

    @admin.action(description="Desativar regras selecionadas")
    def disable_rules(self, request, queryset):
        updated = queryset.update(enabled=False)
        self.message_user(request, f"{updated} regra(s) desativada(s).")
