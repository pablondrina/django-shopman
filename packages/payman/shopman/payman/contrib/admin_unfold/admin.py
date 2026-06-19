"""
Payman Admin with Unfold theme.

Unfold-styled admin for PaymentIntent and PaymentTransaction. Registered when
'shopman.payman.contrib.admin_unfold' is in INSTALLED_APPS; the core ``payman.admin``
guards against double registration.

Both models are mutated exclusively through ``PaymentService`` (and the immutable
``PaymentTransaction`` contract), so these admins are read-only views for operators.
"""

import json
import logging
from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _
from shopman.payman.models import PaymentIntent, PaymentTransaction
from shopman.payman.service import PaymentService
from shopman.utils.contrib.admin_unfold.badges import unfold_badge, unfold_badge_numeric
from shopman.utils.contrib.admin_unfold.base import BaseModelAdmin, BaseTabularInline
from shopman.utils.monetary import format_money
from unfold.contrib.filters.admin.choice_filters import ChoicesRadioFilter
from unfold.decorators import action, display
from unfold.enums import ActionVariant
from unfold.widgets import UnfoldAdminDecimalFieldWidget

logger = logging.getLogger(__name__)


class RefundForm(forms.Form):
    """Valor do reembolso em Reais. Em branco = total disponível (capturado − já reembolsado)."""

    amount_reais = forms.DecimalField(
        label=_("Valor a reembolsar (R$)"),
        required=False,
        min_value=Decimal("0.01"),
        max_digits=10,
        decimal_places=2,
        widget=UnfoldAdminDecimalFieldWidget,
        help_text=_("Deixe em branco para reembolsar o total disponível."),
    )

# Rótulos amigáveis para as chaves de gateway_data (heterogêneas por gateway).
_GATEWAY_LABELS = {
    "txid": _("TXID (PIX)"),
    "location": _("Location (PIX)"),
    "qrcode": _("QR Code (copia e cola)"),
    "imagemQrcode": _("Imagem do QR"),
    "checkout_url": _("URL de checkout"),
    "checkout_session_id": _("Sessão de checkout"),
    "client_secret": _("Client secret"),
    "efi_status": _("Status EFI"),
}


def _gateway_rows(data: dict):
    """Achata gateway_data em (rótulo, valor) legíveis, expandindo o client_secret
    (que pode ser um JSON com qrcode/txid no PIX da EFI) e cortando ruído base64."""
    rows: list[tuple[str, str]] = []
    for key, value in data.items():
        if key == "client_secret" and isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (ValueError, TypeError):
                parsed = None
            if isinstance(parsed, dict):
                for inner_key, inner_value in parsed.items():
                    label = _GATEWAY_LABELS.get(inner_key, inner_key)
                    text = "[imagem base64]" if inner_key == "imagemQrcode" else str(inner_value)
                    rows.append((label, text[:300]))
                continue
        label = _GATEWAY_LABELS.get(key, key)
        text = "[imagem base64]" if key == "imagemQrcode" else str(value)
        rows.append((label, text[:300]))
    return rows

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
        "gateway_data_display",
        "idempotency_key",
        "created_at",
        "authorized_at",
        "captured_at",
        "cancelled_at",
        "expires_at",
        "cancel_reason",
    )
    fieldsets = (
        (_("Identificação"), {"fields": ("ref", "order_ref", "idempotency_key")}),
        (_("Pagamento"), {"fields": ("method", "status", "amount_q", "currency")}),
        (_("Gateway"), {"fields": ("gateway", "gateway_id", "gateway_data_display")}),
        (
            _("Datas"),
            {
                "fields": (
                    "created_at", "authorized_at", "captured_at",
                    "cancelled_at", "expires_at", "cancel_reason",
                ),
            },
        ),
    )
    inlines = [PaymentTransactionInline]
    ordering = ("-created_at",)
    compressed_fields = True
    actions = ["refund_selected"]
    actions_row = ["refund_row"]
    actions_detail = ["refund_detail"]

    @action(
        description=_("Reembolsar (total)"),
        url_path="refund",
        icon="undo",
        variant=ActionVariant.DANGER,
    )
    def refund_row(self, request, object_id):
        intent = self.get_object(request, object_id)
        if intent is None:
            messages.error(request, _("Intent não encontrado."))
            return HttpResponseRedirect(reverse("admin:payman_paymentintent_changelist"))
        self._refund_one(request, intent)
        return HttpResponseRedirect(reverse("admin:payman_paymentintent_change", args=[intent.pk]))

    @action(
        description=_("Reembolsar (parcial/total)"),
        url_path="refund-amount",
        icon="undo",
        variant=ActionVariant.DANGER,
    )
    def refund_detail(self, request, object_id):
        """Intermediate page to refund a specific amount (or total if left blank)."""
        intent = self.get_object(request, object_id)
        if intent is None:
            messages.error(request, _("Intent não encontrado."))
            return HttpResponseRedirect(reverse("admin:payman_paymentintent_changelist"))

        change_url = reverse("admin:payman_paymentintent_change", args=[intent.pk])
        available_q = max(intent.amount_q - PaymentService.refunded_total(intent.ref), 0)

        if request.method == "POST":
            form = RefundForm(request.POST)
            if form.is_valid():
                amount = form.cleaned_data.get("amount_reais")
                amount_q = int((amount * 100).to_integral_value()) if amount is not None else None
                if amount_q is not None and amount_q > available_q:
                    form.add_error(
                        "amount_reais",
                        _("Valor acima do disponível (R$ %(v)s).") % {"v": format_money(available_q)},
                    )
                else:
                    self._refund_one(request, intent, amount_q=amount_q)
                    return HttpResponseRedirect(change_url)
        else:
            form = RefundForm()

        context = {
            **self.admin_site.each_context(request),
            "title": _("Reembolso — %(ref)s") % {"ref": intent.ref},
            "form": form,
            "intent": intent,
            "available_display": format_money(available_q),
            "back_url": change_url,
            "opts": self.model._meta,
        }
        return render(request, "admin/payman/payment_refund.html", context)

    @admin.action(description=_("Reembolsar total dos selecionados"))
    def refund_selected(self, request, queryset):
        done = 0
        for intent in queryset:
            if self._refund_one(request, intent, quiet=True):
                done += 1
        if done:
            messages.success(request, _("%(n)d reembolso(s) processado(s).") % {"n": done})
        if done < queryset.count():
            messages.warning(
                request,
                _("%(n)d intent(s) não puderam ser reembolsados (sem saldo capturado).")
                % {"n": queryset.count() - done},
            )

    def _refund_one(self, request, intent, *, amount_q: int | None = None, quiet: bool = False) -> bool:
        """Refund ``amount_q`` (or the full remaining balance if None). Returns True on success."""
        try:
            transaction = PaymentService.refund(
                intent.ref, amount_q=amount_q, reason="Reembolso via admin"
            )
        except Exception as exc:  # PaymentService valida elegibilidade e levanta
            logger.warning("refund failed for %s: %s", intent.ref, exc)
            if not quiet:
                messages.error(request, str(exc))
            return False
        if not quiet:
            messages.success(
                request,
                _("Reembolso de R$ %(v)s processado para %(ref)s.")
                % {"v": format_money(transaction.amount_q), "ref": intent.ref},
            )
        return True

    @display(description=_("Dados do gateway"))
    def gateway_data_display(self, obj):
        data = obj.gateway_data or {}
        if not data:
            return "—"
        rows = format_html_join(
            "",
            '<div class="flex gap-3 py-1 border-b border-base-100 dark:border-base-800">'
            '<dt class="font-medium text-base-500 dark:text-base-400 w-48 shrink-0">{}</dt>'
            '<dd class="font-mono text-sm break-all">{}</dd></div>',
            _gateway_rows(data),
        )
        return format_html('<dl class="flex flex-col">{}</dl>', rows)

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
