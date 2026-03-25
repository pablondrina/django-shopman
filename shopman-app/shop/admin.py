from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Coupon, Promotion, Shop


@admin.register(Shop)
class ShopAdmin(ModelAdmin):
    fieldsets = (
        ("Identidade", {
            "fields": ("name", "legal_name", "document"),
        }),
        ("Localização", {
            "fields": ("address", "city", "state", "postal_code", "phone", "default_ddd"),
        }),
        ("Operação", {
            "fields": ("currency", "timezone", "opening_hours"),
        }),
        ("Branding", {
            "fields": ("brand_name", "short_name", "tagline", "description",
                       "primary_color", "background_color", "logo_url"),
        }),
        ("Redes e Contatos", {
            "fields": ("website", "instagram", "whatsapp"),
        }),
        ("Defaults de Negócio", {
            "fields": ("defaults",),
            "classes": ("collapse",),
        }),
    )

    def has_add_permission(self, request):
        return not Shop.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = Shop.objects.first()
        if obj:
            return self.changeform_view(request, str(obj.pk), extra_context=extra_context)
        return super().changelist_view(request, extra_context=extra_context)


class CouponInline(admin.TabularInline):
    model = Coupon
    extra = 1
    fields = ("code", "max_uses", "uses_count", "is_active")
    readonly_fields = ("uses_count",)


@admin.register(Promotion)
class PromotionAdmin(ModelAdmin):
    list_display = ("name", "type", "value", "valid_from", "valid_until", "is_active")
    list_filter = ("is_active", "type")
    search_fields = ("name",)
    inlines = [CouponInline]


@admin.register(Coupon)
class CouponAdmin(ModelAdmin):
    list_display = ("code", "promotion", "max_uses", "uses_count", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "promotion__name")
    readonly_fields = ("uses_count",)
