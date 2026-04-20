"""
Basic Django admin for shopman.refs.

For Unfold-themed admin, install shopman.refs.contrib.admin_unfold instead.
"""

from django.contrib import admin

from shopman.refs.models import Ref, RefSequence

_REF_READONLY = [
    "id", "ref_type", "value",
    "target_type", "target_id",
    "scope", "actor",
    "created_at", "deactivated_at", "deactivated_by",
    "metadata",
]


@admin.register(Ref)
class RefAdmin(admin.ModelAdmin):
    list_display = ["ref_type", "value", "target_type", "target_id", "is_active", "created_at"]
    list_filter = ["ref_type", "is_active", "target_type"]
    search_fields = ["value", "target_id", "actor"]
    readonly_fields = _REF_READONLY
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False


@admin.register(RefSequence)
class RefSequenceAdmin(admin.ModelAdmin):
    list_display = ["sequence_name", "scope_hash", "last_value"]
    search_fields = ["sequence_name", "scope_hash"]
    readonly_fields = ["id", "sequence_name", "scope_hash", "scope", "last_value"]
    ordering = ["sequence_name", "scope_hash"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
