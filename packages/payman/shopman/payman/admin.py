from django.contrib import admin
from shopman.payman.models import PaymentIntent, PaymentTransaction


class PaymentTransactionInline(admin.TabularInline):
    model = PaymentTransaction
    extra = 0
    readonly_fields = ("type", "amount_q", "gateway_id", "created_at")


@admin.register(PaymentIntent)
class PaymentIntentAdmin(admin.ModelAdmin):
    list_display = ("ref", "order_ref", "method", "status", "amount_q", "currency", "created_at")
    list_filter = ("status", "method", "currency")
    search_fields = ("ref", "order_ref", "gateway_id")
    readonly_fields = ("created_at", "authorized_at", "captured_at", "cancelled_at")
    inlines = [PaymentTransactionInline]


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ("intent", "type", "amount_q", "gateway_id", "created_at")
    list_filter = ("type",)
    search_fields = ("intent__ref", "gateway_id")
    readonly_fields = ("created_at",)
