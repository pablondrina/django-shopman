"""Admin for RuleConfig, Promotion, Coupon — configurable rules via Unfold."""

from __future__ import annotations

from django.contrib import admin
from django.utils import timezone
from unfold.admin import ModelAdmin

from shopman.models import Coupon, Promotion, RuleConfig

# ── RuleConfig ────────────────────────────────────────────────────────


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


# ── Promotion ─────────────────────────────────────────────────────────


class CouponInline(admin.TabularInline):
    model = Coupon
    extra = 1
    fields = ("code", "max_uses", "uses_count", "is_active")
    readonly_fields = ("uses_count",)


class PromotionStatusFilter(admin.SimpleListFilter):
    title = "situação"
    parameter_name = "situacao"

    def lookups(self, request, model_admin):
        return [
            ("ativa", "Ativa agora"),
            ("futura", "Futura"),
            ("expirada", "Expirada"),
        ]

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == "ativa":
            return queryset.filter(is_active=True, valid_from__lte=now, valid_until__gte=now)
        if self.value() == "futura":
            return queryset.filter(is_active=True, valid_from__gt=now)
        if self.value() == "expirada":
            return queryset.filter(valid_until__lt=now)
        return queryset


@admin.register(Promotion)
class PromotionAdmin(ModelAdmin):
    list_display = (
        "name", "type", "value_display", "valid_from", "valid_until",
        "is_active", "status_display",
    )
    list_filter = (PromotionStatusFilter, "is_active", "type")
    search_fields = ("name",)
    inlines = [CouponInline]

    @admin.display(description="desconto", ordering="value")
    def value_display(self, obj):
        if obj.type == Promotion.PERCENT:
            return f"{obj.value}%"
        return f"R$ {obj.value / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    @admin.display(description="situação", boolean=True)
    def status_display(self, obj):
        now = timezone.now()
        if not obj.is_active:
            return False
        return obj.valid_from <= now <= obj.valid_until


# ── Coupon ────────────────────────────────────────────────────────────


@admin.register(Coupon)
class CouponAdmin(ModelAdmin):
    list_display = (
        "code", "promotion", "usage_display", "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("code", "promotion__name")
    readonly_fields = ("uses_count",)

    @admin.display(description="uso")
    def usage_display(self, obj):
        if obj.max_uses == 0:
            return f"{obj.uses_count} (ilimitado)"
        return f"{obj.uses_count}/{obj.max_uses}"
