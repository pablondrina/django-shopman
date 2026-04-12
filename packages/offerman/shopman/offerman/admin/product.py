"""Product admin."""

from django.contrib import admin
from django.utils.html import format_html

from shopman.offerman.models import Product, ProductComponent


class ProductComponentInline(admin.TabularInline):
    model = ProductComponent
    fk_name = "parent"
    extra = 1
    autocomplete_fields = ["component"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    autocomplete_extra_fields = ["base_price_q"]
    list_display = [
        "sku",
        "name",
        "formatted_price",
        "visibility_status",
        "is_bundle_display",
    ]
    list_filter = [
        "is_published",
        "is_sellable",
        "availability_policy",
    ]
    search_fields = ["sku", "name", "keywords__name"]
    readonly_fields = ["uuid", "created_at", "updated_at", "is_bundle", "margin_percent", "is_perishable"]
    inlines = [ProductComponentInline]

    fieldsets = [
        (
            None,
            {"fields": ("sku", "name", "short_description", "long_description", "keywords")},
        ),
        (
            "Price & Cost",
            {"fields": ("base_price_q", "margin_percent")},
        ),
        (
            "Publication & Sellability",
            {
                "fields": ("is_published", "is_sellable"),
                "description": "is_published controls catalog exposure, is_sellable controls whether the product is commercially enabled.",
            },
        ),
        (
            "Configuration",
            {
                "fields": (
                    "unit",
                    "availability_policy",
                    "shelf_life_days",
                    "is_perishable",
                    "production_cycle_hours",
                    "is_batch_produced",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": ("metadata", "uuid", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    ]

    def formatted_price(self, obj):
        return f"R$ {obj.base_price_q / 100:.2f}"

    formatted_price.short_description = "Price"
    formatted_price.admin_order_field = "base_price_q"

    def visibility_status(self, obj):
        """Display visibility status with colored badges."""
        badges = []

        if not obj.is_published:
            badges.append(
                '<span style="background-color:#ffc107;color:#000;'
                'padding:2px 6px;border-radius:3px;font-size:11px;">Unpublished</span>'
            )
        if not obj.is_sellable:
            badges.append(
                '<span style="background-color:#dc3545;color:#fff;'
                'padding:2px 6px;border-radius:3px;font-size:11px;">Not Sellable</span>'
            )

        if not badges:
            return format_html(
                '<span style="background-color:#28a745;color:#fff;'
                'padding:2px 6px;border-radius:3px;font-size:11px;">Active</span>'
            )

        return format_html(" ".join(badges))

    visibility_status.short_description = "Status"

    def is_bundle_display(self, obj):
        return obj.is_bundle

    is_bundle_display.boolean = True
    is_bundle_display.short_description = "Bundle"

    actions = ["unpublish_products", "publish_products", "pause_products", "resume_products"]

    @admin.action(description="Unpublish selected products")
    def unpublish_products(self, request, queryset):
        updated = queryset.update(is_published=False)
        self.message_user(request, f"{updated} product(s) unpublished.")

    @admin.action(description="Publish selected products")
    def publish_products(self, request, queryset):
        updated = queryset.update(is_published=True)
        self.message_user(request, f"{updated} product(s) published.")

    @admin.action(description="Disable selling for selected products")
    def pause_products(self, request, queryset):
        updated = queryset.update(is_sellable=False)
        self.message_user(request, f"{updated} product(s) disabled for sale.")

    @admin.action(description="Enable selling for selected products")
    def resume_products(self, request, queryset):
        updated = queryset.update(is_sellable=True)
        self.message_user(request, f"{updated} product(s) enabled for sale.")
