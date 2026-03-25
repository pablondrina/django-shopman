"""Customers admin (CORE only).

Contrib models have their own admin in their respective modules:
- customers.contrib.identifiers.admin: CustomerIdentifierAdmin
- customers.contrib.preferences.admin: CustomerPreferenceAdmin
- customers.contrib.insights.admin: CustomerInsightAdmin
"""

from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

from shopman.customers.contrib.merge.admin import MergeAdminMixin
from shopman.customers.models import (
    Customer,
    CustomerGroup,
    CustomerAddress,
    ContactPoint,
    ExternalIdentity,
)


# ===========================================
# CustomerGroup Admin
# ===========================================


@admin.register(CustomerGroup)
class CustomerGroupAdmin(admin.ModelAdmin):
    list_display = [
        "ref",
        "name",
        "listing_ref",
        "priority",
        "is_default",
        "customer_count",
    ]
    list_filter = ["is_default"]
    search_fields = ["ref", "name"]
    ordering = ["-priority", "name"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_customer_count=Count("customers"))

    def customer_count(self, obj):
        return obj._customer_count

    customer_count.short_description = "Customers"
    customer_count.admin_order_field = "_customer_count"


# ===========================================
# Inline Classes (must be defined before CustomerAdmin)
# ===========================================


class CustomerAddressInline(admin.TabularInline):
    model = CustomerAddress
    extra = 0
    fields = ["label", "formatted_address", "is_default", "is_verified"]
    readonly_fields = ["is_verified"]


class ContactPointInline(admin.TabularInline):
    model = ContactPoint
    extra = 0
    fields = ["type", "value_normalized", "is_primary", "is_verified", "verification_method"]
    readonly_fields = ["verification_method"]


class ExternalIdentityInline(admin.TabularInline):
    model = ExternalIdentity
    extra = 0
    fields = ["provider", "provider_uid", "is_active"]
    readonly_fields = ["provider_uid"]


# Optional inlines from contrib modules
_optional_inlines = []

try:
    from shopman.customers.contrib.consent.models import CommunicationConsent

    class CommunicationConsentInline(admin.TabularInline):
        model = CommunicationConsent
        extra = 0
        fields = ["channel", "status", "legal_basis", "source", "consented_at", "revoked_at"]
        readonly_fields = ["consented_at", "revoked_at"]

    _optional_inlines.append(CommunicationConsentInline)
except ImportError:
    pass

try:
    from shopman.customers.contrib.timeline.models import TimelineEvent

    class RecentTimelineInline(admin.TabularInline):
        model = TimelineEvent
        extra = 0
        fields = ["event_type", "title", "channel", "created_at"]
        readonly_fields = ["event_type", "title", "channel", "created_at"]
        ordering = ["-created_at"]
        max_num = 10
        verbose_name_plural = "Timeline (últimos 10)"

        def has_add_permission(self, request, obj=None):
            return False

        def has_delete_permission(self, request, obj=None):
            return False

    _optional_inlines.append(RecentTimelineInline)
except ImportError:
    pass


# ===========================================
# Customer Admin
# ===========================================


@admin.register(Customer)
class CustomerAdmin(MergeAdminMixin, admin.ModelAdmin):
    list_display = [
        "ref",
        "name",
        "customer_type",
        "group",
        "phone",
        "is_active",
    ]
    list_filter = ["customer_type", "group", "is_active"]
    search_fields = ["ref", "first_name", "last_name", "document", "phone", "email"]
    list_editable = ["is_active"]
    actions = ["merge_customers_action"]
    readonly_fields = ["uuid", "created_at", "updated_at"]
    inlines = [
        CustomerAddressInline,
        ContactPointInline,
        ExternalIdentityInline,
    ] + _optional_inlines

    fieldsets = [
        (
            "Identification",
            {
                "fields": [
                    "ref",
                    "uuid",
                    "first_name",
                    "last_name",
                    "customer_type",
                    "document",
                ]
            },
        ),
        ("Contact", {"fields": ["email", "phone"]}),
        ("Segmentation", {"fields": ["group", "notes"]}),
        (
            "System",
            {
                "fields": [
                    "is_active",
                    "metadata",
                    "created_at",
                    "updated_at",
                    "created_by",
                    "source_system",
                ],
                "classes": ["collapse"],
            },
        ),
    ]


# ===========================================
# CustomerAddress Admin
# ===========================================


@admin.register(CustomerAddress)
class CustomerAddressAdmin(admin.ModelAdmin):
    list_display = [
        "customer",
        "label",
        "formatted_address",
        "is_default",
        "is_verified",
    ]
    list_filter = ["label", "is_default", "is_verified"]
    search_fields = ["customer__ref", "customer__first_name", "formatted_address"]
    raw_id_fields = ["customer"]


# ===========================================
# ContactPoint Admin
# ===========================================


@admin.register(ContactPoint)
class ContactPointAdmin(admin.ModelAdmin):
    list_display = [
        "value_masked",
        "type",
        "customer_link",
        "is_primary",
        "verified_badge",
        "created_at",
    ]
    list_filter = ["type", "is_primary", "is_verified", "verification_method"]
    search_fields = ["value_normalized", "customer__ref", "customer__first_name"]
    raw_id_fields = ["customer"]
    readonly_fields = ["id", "verified_at", "created_at", "updated_at"]

    fieldsets = [
        (None, {"fields": ["id", "customer", "type", "value_normalized", "value_display"]}),
        ("Status", {"fields": ["is_primary", "is_verified"]}),
        (
            "Verification",
            {"fields": ["verification_method", "verified_at", "verification_ref"]},
        ),
        ("Timestamps", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    def value_masked(self, obj):
        return obj.value_masked

    value_masked.short_description = "Value"

    def customer_link(self, obj):
        from django.urls import reverse

        url = reverse("admin:customers_customer_change", args=[obj.customer.pk])
        return format_html(
            '<a href="{}">{}</a>',
            url,
            obj.customer.ref,
        )

    customer_link.short_description = "Customer"

    def verified_badge(self, obj):
        if obj.is_verified:
            return format_html('<span style="color: green;">V</span>')
        return format_html('<span style="color: gray;">o</span>')

    verified_badge.short_description = "Verified"


# ===========================================
# ExternalIdentity Admin
# ===========================================


@admin.register(ExternalIdentity)
class ExternalIdentityAdmin(admin.ModelAdmin):
    list_display = [
        "provider",
        "provider_uid_short",
        "customer_link",
        "is_active",
        "created_at",
    ]
    list_filter = ["provider", "is_active"]
    search_fields = ["provider_uid", "customer__ref", "customer__first_name"]
    raw_id_fields = ["customer"]
    readonly_fields = ["id", "created_at", "updated_at"]

    fieldsets = [
        (None, {"fields": ["id", "customer", "provider", "provider_uid"]}),
        ("Status", {"fields": ["is_active"]}),
        ("Metadata", {"fields": ["provider_meta"], "classes": ["collapse"]}),
        ("Timestamps", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    def provider_uid_short(self, obj):
        if len(obj.provider_uid) > 20:
            return obj.provider_uid[:20] + "..."
        return obj.provider_uid

    provider_uid_short.short_description = "Provider UID"

    def customer_link(self, obj):
        from django.urls import reverse

        url = reverse("admin:customers_customer_change", args=[obj.customer.pk])
        return format_html(
            '<a href="{}">{}</a>',
            url,
            obj.customer.ref,
        )

    customer_link.short_description = "Customer"
