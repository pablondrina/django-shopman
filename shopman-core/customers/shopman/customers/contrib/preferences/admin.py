"""Admin for CustomerPreference."""

from django.contrib import admin

from shopman.customers.contrib.preferences.models import CustomerPreference


@admin.register(CustomerPreference)
class CustomerPreferenceAdmin(admin.ModelAdmin):
    list_display = [
        "customer",
        "category",
        "key",
        "value",
        "preference_type",
        "confidence",
        "updated_at",
    ]
    list_filter = ["preference_type", "category"]
    search_fields = ["customer__ref", "customer__first_name", "key"]
    readonly_fields = ["created_at", "updated_at"]
    raw_id_fields = ["customer"]
