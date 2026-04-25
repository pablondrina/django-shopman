"""
Auth Admin with Unfold theme.

This module provides Unfold-styled admin classes for Auth models.
To use, add 'shopman.doorman.contrib.admin_unfold' to INSTALLED_APPS after 'shopman.doorman'.

The admins will automatically unregister the basic admins and register
the Unfold versions.
"""

from django.contrib import admin
from shopman.doorman.models import AccessLink, CustomerUser, TrustedDevice, VerificationCode
from shopman.utils.contrib.admin_unfold.badges import unfold_badge
from shopman.utils.contrib.admin_unfold.base import BaseModelAdmin
from unfold.decorators import display

# Unregister basic admins
for model in [CustomerUser, AccessLink, VerificationCode, TrustedDevice]:
    try:
        admin.site.unregister(model)
    except admin.sites.NotRegistered:
        pass


# =============================================================================
# CUSTOMER USER ADMIN
# =============================================================================


@admin.register(CustomerUser)
class CustomerUserAdmin(BaseModelAdmin):
    list_display = ["id", "user", "customer_id_short", "created_at"]
    search_fields = ["user__username", "customer_id"]
    readonly_fields = ["user", "customer_id", "created_at", "metadata"]
    ordering = ["-created_at"]

    fieldsets = [
        (None, {"fields": ["user", "customer_id"]}),
        ("Metadata", {"fields": ["metadata", "created_at"], "classes": ["collapse"]}),
    ]

    @display(description="Customer ID")
    def customer_id_short(self, obj):
        return str(obj.customer_id)[:8] + "…"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# =============================================================================
# ACCESS LINK ADMIN
# =============================================================================


@admin.register(AccessLink)
class AccessLinkAdmin(BaseModelAdmin):
    list_display = [
        "token_short",
        "customer_id_short",
        "audience_badge",
        "source_badge",
        "status_badge",
        "created_at",
    ]
    list_filter = ["audience", "source"]
    search_fields = ["token_hash", "customer_id"]
    readonly_fields = [
        "id",
        "token_hash",
        "customer_id",
        "audience",
        "source",
        "created_at",
        "expires_at",
        "used_at",
        "user",
        "metadata",
    ]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"

    fieldsets = [
        (None, {"fields": ["id", "token_hash", "customer_id"]}),
        ("Scope", {"fields": ["audience", "source"]}),
        ("Lifecycle", {"fields": ["created_at", "expires_at", "used_at"]}),
        ("Result", {"fields": ["user"]}),
        ("Metadata", {"fields": ["metadata"], "classes": ["collapse"]}),
    ]

    @display(description="Token Hash")
    def token_short(self, obj):
        return obj.token_hash[:12] + "…"

    @display(description="Customer")
    def customer_id_short(self, obj):
        return str(obj.customer_id)[:8] + "…"

    @display(description="Audience")
    def audience_badge(self, obj):
        colors = {
            "web_checkout": "green",
            "web_account": "blue",
            "web_support": "yellow",
            "web_general": "base",
        }
        color = colors.get(obj.audience, "base")
        return unfold_badge(obj.get_audience_display(), color)

    @display(description="Source")
    def source_badge(self, obj):
        colors = {
            "manychat": "blue",
            "internal": "base",
            "api": "green",
        }
        color = colors.get(obj.source, "base")
        return unfold_badge(obj.get_source_display(), color)

    @display(description="Status")
    def status_badge(self, obj):
        if obj.used_at:
            return unfold_badge("Used", "blue")
        elif obj.is_expired:
            return unfold_badge("Expired", "base")
        else:
            return unfold_badge("Valid", "green")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# =============================================================================
# VERIFICATION CODE ADMIN
# =============================================================================


@admin.register(VerificationCode)
class VerificationCodeAdmin(BaseModelAdmin):
    list_display = [
        "code_hash_short",
        "target_masked",
        "purpose_badge",
        "delivery_badge",
        "status_badge",
        "attempts_display",
        "created_at",
    ]
    list_filter = ["status", "purpose", "delivery_method"]
    search_fields = ["target_value", "customer_id"]
    readonly_fields = [
        "id",
        "code_hash",
        "target_value",
        "purpose",
        "status",
        "created_at",
        "expires_at",
        "sent_at",
        "verified_at",
        "delivery_method",
        "attempts",
        "max_attempts",
        "ip_address",
        "customer_id",
    ]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"

    fieldsets = [
        (None, {"fields": ["id", "code_hash", "target_value"]}),
        ("Purpose", {"fields": ["purpose", "delivery_method"]}),
        ("Lifecycle", {"fields": ["status", "created_at", "expires_at", "sent_at", "verified_at"]}),
        ("Security", {"fields": ["attempts", "max_attempts", "ip_address"]}),
        ("Result", {"fields": ["customer_id"]}),
    ]

    @display(description="Code Hash")
    def code_hash_short(self, obj):
        return obj.code_hash[:12] + "…"

    @display(description="Target")
    def target_masked(self, obj):
        value = obj.target_value
        if "@" in value:
            parts = value.split("@")
            local = parts[0]
            domain = parts[1]
            masked = local[0] + "***" + local[-1] if len(local) > 2 else "***"
            return f"{masked}@{domain}"
        elif len(value) > 4:
            return "***" + value[-4:]
        return "****"

    @display(description="Purpose")
    def purpose_badge(self, obj):
        colors = {"login": "blue", "verify_contact": "green"}
        color = colors.get(obj.purpose, "base")
        return unfold_badge(obj.get_purpose_display(), color)

    @display(description="Method")
    def delivery_badge(self, obj):
        colors = {"whatsapp": "green", "sms": "blue", "email": "yellow"}
        color = colors.get(obj.delivery_method, "base")
        return unfold_badge(obj.get_delivery_method_display(), color)

    @display(description="Status")
    def status_badge(self, obj):
        colors = {
            "pending": "yellow",
            "sent": "blue",
            "verified": "green",
            "expired": "base",
            "failed": "red",
        }
        color = colors.get(obj.status, "base")
        return unfold_badge(obj.get_status_display(), color)

    @display(description="Attempts")
    def attempts_display(self, obj):
        text = f"{obj.attempts}/{obj.max_attempts}"
        if obj.attempts >= obj.max_attempts:
            return unfold_badge(text, "red")
        return text

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# =============================================================================
# TRUSTED DEVICE ADMIN
# =============================================================================


@admin.register(TrustedDevice)
class TrustedDeviceAdmin(BaseModelAdmin):
    list_display = [
        "token_hash_short",
        "customer_id_short",
        "label",
        "status_badge",
        "last_used_at",
        "created_at",
    ]
    list_filter = ["is_active"]
    search_fields = ["customer_id", "label"]
    readonly_fields = [
        "id",
        "customer_id",
        "token_hash",
        "user_agent",
        "ip_address",
        "label",
        "created_at",
        "expires_at",
        "last_used_at",
        "is_active",
    ]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"

    fieldsets = [
        (None, {"fields": ["id", "customer_id", "token_hash"]}),
        ("Device", {"fields": ["label", "user_agent", "ip_address"]}),
        ("Lifecycle", {"fields": ["created_at", "expires_at", "last_used_at", "is_active"]}),
    ]

    actions = ["revoke_selected"]

    @display(description="Token Hash")
    def token_hash_short(self, obj):
        return obj.token_hash[:12] + "…"

    @display(description="Customer")
    def customer_id_short(self, obj):
        return str(obj.customer_id)[:8] + "…"

    @display(description="Status")
    def status_badge(self, obj):
        if not obj.is_active:
            return unfold_badge("Revoked", "red")
        elif obj.is_expired:
            return unfold_badge("Expired", "base")
        else:
            return unfold_badge("Active", "green")

    @admin.action(description="Revoke selected devices")
    def revoke_selected(self, request, queryset):
        count = queryset.filter(is_active=True).update(is_active=False)
        self.message_user(request, f"{count} device(s) revoked.")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
