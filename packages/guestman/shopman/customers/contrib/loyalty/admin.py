"""Loyalty admin."""

from django.contrib import admin
from django.utils.html import format_html

from shopman.customers.contrib.loyalty.models import LoyaltyAccount, LoyaltyTransaction


class LoyaltyTransactionInline(admin.TabularInline):
    model = LoyaltyTransaction
    extra = 0
    readonly_fields = ["transaction_type", "points", "balance_after", "description", "reference", "created_at"]
    ordering = ["-created_at"]

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LoyaltyAccount)
class LoyaltyAccountAdmin(admin.ModelAdmin):
    list_display = [
        "customer_link",
        "points_balance",
        "lifetime_points",
        "tier_badge",
        "stamps_progress",
        "is_active",
        "enrolled_at",
    ]
    list_filter = ["tier", "is_active"]
    search_fields = ["customer__ref", "customer__first_name"]
    raw_id_fields = ["customer"]
    readonly_fields = ["enrolled_at", "updated_at"]
    inlines = [LoyaltyTransactionInline]

    def tier_badge(self, obj):
        colors = {
            "bronze": "#cd7f32",
            "silver": "#c0c0c0",
            "gold": "#ffd700",
            "platinum": "#e5e4e2",
        }
        color = colors.get(obj.tier, "#6c757d")
        text_color = "#000" if obj.tier in ("gold", "silver", "platinum") else "#fff"
        return format_html(
            '<span style="background:{}; color:{}; padding:2px 8px; '
            'border-radius:3px; font-size:11px;">{}</span>',
            color,
            text_color,
            obj.get_tier_display(),
        )

    tier_badge.short_description = "Nível"

    def stamps_progress(self, obj):
        pct = obj.stamps_progress_percent
        return format_html(
            '{}/{} ({}%) — {} completas',
            obj.stamps_current,
            obj.stamps_target,
            pct,
            obj.stamps_completed,
        )

    stamps_progress.short_description = "Carimbos"

    def customer_link(self, obj):
        from django.urls import reverse

        url = reverse("admin:customers_customer_change", args=[obj.customer.pk])
        return format_html('<a href="{}">{}</a>', url, obj.customer.ref)

    customer_link.short_description = "Cliente"


@admin.register(LoyaltyTransaction)
class LoyaltyTransactionAdmin(admin.ModelAdmin):
    list_display = [
        "created_at",
        "customer_ref",
        "transaction_type",
        "points_display",
        "balance_after",
        "description",
    ]
    list_filter = ["transaction_type"]
    search_fields = ["account__customer__ref", "description", "reference"]
    readonly_fields = [
        "account",
        "transaction_type",
        "points",
        "balance_after",
        "description",
        "reference",
        "created_at",
        "created_by",
    ]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def customer_ref(self, obj):
        return obj.account.customer.ref

    customer_ref.short_description = "Cliente"

    def points_display(self, obj):
        if obj.points > 0:
            return format_html('<span style="color:green">+{}</span>', obj.points)
        return format_html('<span style="color:red">{}</span>', obj.points)

    points_display.short_description = "Pontos"
