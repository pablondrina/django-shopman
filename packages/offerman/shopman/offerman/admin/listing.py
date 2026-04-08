"""Listing admin."""

from django.contrib import admin

from shopman.utils.admin.mixins import AutofillInlineMixin
from shopman.offerman.models import Listing, ListingItem


class ListingItemInline(AutofillInlineMixin, admin.TabularInline):
    model = ListingItem
    extra = 1
    autocomplete_fields = ["product"]
    autofill_fields = {"product": {"price_q": "base_price_q"}}
    fields = ["product", "price_q", "min_qty", "is_published", "is_available"]


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = [
        "ref",
        "name",
        "is_active",
        "valid_from",
        "valid_until",
        "priority",
        "items_count",
    ]
    list_filter = ["is_active"]
    search_fields = ["ref", "name"]
    list_editable = ["is_active", "priority"]
    ordering = ["-priority", "name"]
    inlines = [ListingItemInline]

    fieldsets = [
        (None, {"fields": ("ref", "name", "description")}),
        ("Validity", {"fields": ("valid_from", "valid_until")}),
        ("Settings", {"fields": ("priority", "is_active")}),
    ]

    def save_formset(self, request, form, formset, change):
        """Default price_q to product.base_price_q when left blank."""
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, ListingItem) and instance.product_id:
                if not instance.price_q:
                    instance.price_q = instance.product.base_price_q
            instance.save()
        for obj in formset.deleted_objects:
            obj.delete()
        formset.save_m2m()

    def items_count(self, obj):
        return obj.items.count()

    items_count.short_description = "Items"
