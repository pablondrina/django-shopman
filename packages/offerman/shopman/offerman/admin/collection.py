"""Collection admin."""

from django.contrib import admin

from shopman.offerman.models import Collection, CollectionItem


class CollectionItemInline(admin.TabularInline):
    model = CollectionItem
    extra = 1
    autocomplete_fields = ["product"]
    fields = ["product", "is_primary", "sort_order"]


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = [
        "slug",
        "name",
        "parent",
        "is_active",
        "valid_from",
        "valid_until",
        "products_count",
    ]
    list_filter = ["is_active", "parent"]
    search_fields = ["slug", "name"]
    list_editable = ["is_active"]
    ordering = ["sort_order", "name"]
    inlines = [CollectionItemInline]

    fieldsets = [
        (None, {"fields": ("slug", "name", "description")}),
        ("Hierarchy", {"fields": ("parent",)}),
        ("Validity", {"fields": ("valid_from", "valid_until")}),
        ("Settings", {"fields": ("sort_order", "is_active")}),
    ]

    def products_count(self, obj):
        return obj.items.count()

    products_count.short_description = "Products"
