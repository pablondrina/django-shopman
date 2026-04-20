"""Promotion + Coupon admin — storefront discount management."""

from __future__ import annotations

from django.contrib import admin
from django.utils import timezone
from unfold.admin import ModelAdmin

from shopman.storefront.models import Coupon, Promotion


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
