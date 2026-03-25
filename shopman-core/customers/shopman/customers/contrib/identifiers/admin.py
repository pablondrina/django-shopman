"""Admin for CustomerIdentifier."""

from django.contrib import admin

from shopman.customers.contrib.identifiers.models import CustomerIdentifier


@admin.register(CustomerIdentifier)
class CustomerIdentifierAdmin(admin.ModelAdmin):
    list_display = [
        "customer",
        "identifier_type",
        "identifier_value",
        "is_primary",
        "verified_at",
        "created_at",
    ]
    list_filter = ["identifier_type", "is_primary"]
    search_fields = ["customer__ref", "customer__first_name", "identifier_value"]
    readonly_fields = ["created_at"]
    raw_id_fields = ["customer"]
