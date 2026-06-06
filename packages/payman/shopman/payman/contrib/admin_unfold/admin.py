"""
Payman Admin with Unfold theme.

Unfold-styled admin for PaymentIntent and PaymentTransaction. Registered when
'shopman.payman.contrib.admin_unfold' is in INSTALLED_APPS; the core ``payman.admin``
guards against double registration.

Both models are mutated exclusively through ``PaymentService`` (and the immutable
``PaymentTransaction`` contract), so these admins are read-only views for operators.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from shopman.payman.models import PaymentIntent, PaymentTransaction
from shopman.utils.contrib.admin_unfold.badges import unfold_badge, unfold_badge_numeric
from shopman.utils.contrib.admin_unfold.base import BaseModelAdmin, BaseTabularInline
from shopman.utils.monetary import format_money
from unfold.contrib.filters.admin.choice_filters import ChoicesRadioFilter
from unfold.decorators import display

_STATUS_COLORS = {
    PaymentIntent.Status.PENDING: "yellow",
    PaymentIntent.Status.AUTHORIZED: "blue",
    PaymentIntent.Status.CAPTURED: "green",
    PaymentIntent.Status.FAILED: "red",
    PaymentIntent.Status.CANCELLED: "base",
    PaymentIntent.Status.REFUNDED: "orange",
}

_METHOD_COLORS = {
    PaymentIntent.Method.PIX: "green",
    PaymentIntent.Method.CASH: "base",
    PaymentIntent.Method.CARD: "blue",
    PaymentIntent.Method.EXTERNAL: "base",
}

_TRANSACTION_COLORS = {
    PaymentTransaction.Type.CAPTURE: "green",
    PaymentTransaction.Type.REFUND: "yellow",
    PaymentTransaction.Type.CHARGEBACK: "red",
}


def _format_datetime(dt):
    """Format datetime as DD/MM/AA · HH:MM."""
    return dt.strftime("%d/%m/%y · %H:%M") if dt else "—"


# =============================================================================
# TRANSACTION INLINE
# =============================================================================


class PaymentTransactionInline(BaseTabularInline):
    """Immutable financial movements under a PaymentIntent (read-only)."""

    model = PaymentTransaction
    extra = 0
    fields = ("type_badge", "amount_display", "gateway_id", "created_at_display")
    readonly_fields = ("type_badge", "amount_display", "gateway_id", "created_at_display")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description=_("Tipo"))
    def type_badge(self, obj):
        color = _TRANSACTION_COLORS.get(obj.type, "base")
        return unfold_badge(obj.get_type_display().upper(), color)

    @display(description=_("Valor"))
    def amount_display(self, obj):
        return unfold_badge_numeric(f"R$ {format_money(obj.amount_q)}", "base")

    @display(description=_("Data"))
    def created_at_display(self, obj):
        return _format_datetime(obj.created_at)


# =============================================================================
# PAYMENT INTENT ADMIN
# =============================================================================


@admin.register(PaymentIntent)
class PaymentIntentAdmin(BaseModelAdmin):
    """Read-only view of payment intents (mutated via PaymentService)."""

    list_display = (
        "ref",
        "order_ref",
        "method_badge",
        "status_badge",
        "amount_display",
        "currency",
        "created_at_display",
    )
    list_filter = (("status", ChoicesRadioFilter), "method", "currency")
    search_fields = ("ref", "order_ref", "gateway_id")
    readonly_fields = (
        "ref",
        "order_ref",
        "method",
        "status",
        "amount_q",
        "currency",
        "gateway",
        "gateway_id",
        "gateway_data",
        "idempotency_key",
        "created_at",
        "authorized_at",
        "captured_at",
        "cancelled_at",
        "expires_at",
        "cancel_reason",
    )
    inlines = [PaymentTransactionInline]
    ordering = ("-created_at",)
    compressed_fields = True

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description=_("Método"))
    def method_badge(self, obj):
        color = _METHOD_COLORS.get(obj.method, "base")
        return unfold_badge(obj.get_method_display().upper(), color)

    @display(description=_("Status"))
    def status_badge(self, obj):
        color = _STATUS_COLORS.get(obj.status, "base")
        return unfold_badge(obj.get_status_display().upper(), color)

    @display(description=_("Valor"))
    def amount_display(self, obj):
        return unfold_badge_numeric(f"R$ {format_money(obj.amount_q)}", "base")

    @display(description=_("Criado"))
    def created_at_display(self, obj):
        return _format_datetime(obj.created_at)


# =============================================================================
# PAYMENT TRANSACTION ADMIN
# =============================================================================


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(BaseModelAdmin):
    """Read-only audit trail of financial movements (immutable model)."""

    list_display = ("intent", "type_badge", "amount_display", "gateway_id", "created_at_display")
    list_filter = (("type", ChoicesRadioFilter),)
    search_fields = ("intent__ref", "gateway_id")
    readonly_fields = ("intent", "type", "amount_q", "gateway_id", "created_at")
    ordering = ("-created_at",)
    compressed_fields = True

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description=_("Tipo"))
    def type_badge(self, obj):
        color = _TRANSACTION_COLORS.get(obj.type, "base")
        return unfold_badge(obj.get_type_display().upper(), color)

    @display(description=_("Valor"))
    def amount_display(self, obj):
        return unfold_badge_numeric(f"R$ {format_money(obj.amount_q)}", "base")

    @display(description=_("Data"))
    def created_at_display(self, obj):
        return _format_datetime(obj.created_at)
