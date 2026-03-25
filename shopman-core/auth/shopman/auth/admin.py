"""
Auth Django Admin configuration.
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import BridgeToken, IdentityLink, MagicCode, TrustedDevice


# ===========================================
# IdentityLink
# ===========================================


@admin.register(IdentityLink)
class IdentityLinkAdmin(admin.ModelAdmin):
    list_display = ["id", "user_link", "customer_id_short", "created_at"]
    search_fields = ["user__username", "customer_id"]
    readonly_fields = ["user", "customer_id", "created_at", "metadata"]
    ordering = ["-created_at"]

    def user_link(self, obj):
        return format_html(
            '<a href="/admin/auth/user/{}/change/">{}</a>',
            obj.user_id,
            obj.user,
        )

    user_link.short_description = "User"

    def customer_id_short(self, obj):
        return str(obj.customer_id)[:8] + "..."

    customer_id_short.short_description = "Customer ID"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ===========================================
# BridgeToken
# ===========================================


@admin.register(BridgeToken)
class BridgeTokenAdmin(admin.ModelAdmin):
    list_display = [
        "token_short",
        "customer_id_short",
        "audience",
        "source",
        "status_badge",
        "created_at",
    ]
    list_filter = ["audience", "source"]
    search_fields = ["token", "customer_id"]
    readonly_fields = [
        "id",
        "token",
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
        (None, {"fields": ["id", "token", "customer_id"]}),
        ("Scope", {"fields": ["audience", "source"]}),
        ("Lifecycle", {"fields": ["created_at", "expires_at", "used_at"]}),
        ("Result", {"fields": ["user"]}),
        ("Metadata", {"fields": ["metadata"], "classes": ["collapse"]}),
    ]

    def token_short(self, obj):
        return obj.token[:12] + "..."

    token_short.short_description = "Token"

    def customer_id_short(self, obj):
        return str(obj.customer_id)[:8] + "..."

    customer_id_short.short_description = "Customer"

    def status_badge(self, obj):
        if obj.used_at:
            return format_html('<span style="color: blue;">Used</span>')
        elif obj.is_expired:
            return format_html('<span style="color: gray;">Expired</span>')
        else:
            return format_html('<span style="color: green;">Valid</span>')

    status_badge.short_description = "Status"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ===========================================
# MagicCode
# ===========================================


@admin.register(MagicCode)
class MagicCodeAdmin(admin.ModelAdmin):
    list_display = [
        "code_hash_short",
        "target_masked",
        "purpose",
        "delivery_method",
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

    target_masked.short_description = "Target"

    def status_badge(self, obj):
        colors = {
            "pending": "orange",
            "sent": "blue",
            "verified": "green",
            "expired": "gray",
            "failed": "red",
        }
        color = colors.get(obj.status, "gray")
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"

    def attempts_display(self, obj):
        if obj.attempts >= obj.max_attempts:
            return format_html(
                '<span style="color: red;">{}/{}</span>',
                obj.attempts,
                obj.max_attempts,
            )
        return f"{obj.attempts}/{obj.max_attempts}"

    attempts_display.short_description = "Attempts"

    def code_hash_short(self, obj):
        return obj.code_hash[:12] + "..."

    code_hash_short.short_description = "Code Hash"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ===========================================
# TrustedDevice
# ===========================================


@admin.register(TrustedDevice)
class TrustedDeviceAdmin(admin.ModelAdmin):
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

    def token_hash_short(self, obj):
        return obj.token_hash[:12] + "..."

    token_hash_short.short_description = "Token Hash"

    def customer_id_short(self, obj):
        return str(obj.customer_id)[:8] + "..."

    customer_id_short.short_description = "Customer"

    def status_badge(self, obj):
        if not obj.is_active:
            return format_html('<span style="color: red;">Revoked</span>')
        elif obj.is_expired:
            return format_html('<span style="color: gray;">Expired</span>')
        else:
            return format_html('<span style="color: green;">Active</span>')

    status_badge.short_description = "Status"

    @admin.action(description="Revoke selected devices")
    def revoke_selected(self, request, queryset):
        count = queryset.filter(is_active=True).update(is_active=False)
        self.message_user(request, f"{count} device(s) revoked.")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
