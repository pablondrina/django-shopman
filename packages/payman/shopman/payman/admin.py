"""
Payman Admin — basic fallback (works without Unfold).

For the Unfold-styled version, add 'shopman.payman.contrib.admin_unfold' to INSTALLED_APPS.
When the Unfold contrib is loaded, this module does nothing (avoids double registration).
"""

from django.apps import apps
from django.contrib import admin
from shopman.payman.models import PaymentIntent, PaymentTransaction

# Skip registration if the Unfold contrib is installed (it will register its own admins)
if not apps.is_installed("shopman.payman.contrib.admin_unfold"):

    class PaymentTransactionInline(admin.TabularInline):
        model = PaymentTransaction
        extra = 0
        readonly_fields = ("type", "amount_q", "gateway_id", "created_at")

    @admin.register(PaymentIntent)
    class PaymentIntentAdmin(admin.ModelAdmin):
        list_display = ("ref", "order_ref", "method", "status", "amount_q", "currency", "cancel_reason", "created_at")
        list_filter = ("status", "method", "currency")
        search_fields = ("ref", "order_ref", "gateway_id")
        readonly_fields = (
            "created_at",
            "authorized_at",
            "captured_at",
            "cancelled_at",
            "cancel_reason",
            "gateway_id",
            "gateway_data",
            "idempotency_key",
        )
        inlines = [PaymentTransactionInline]

    @admin.register(PaymentTransaction)
    class PaymentTransactionAdmin(admin.ModelAdmin):
        list_display = ("intent", "type", "amount_q", "gateway_id", "created_at")
        list_filter = ("type",)
        search_fields = ("intent__ref", "gateway_id")
        readonly_fields = ("created_at",)
