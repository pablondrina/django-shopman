"""Order, Product, Batch, Quant admin extensions.

Extends Core admins with app-layer features:
- OrderAdmin: Fulfillment inline + payment info
- ProductAdmin: allows_next_day_sale checkbox (via metadata)
- BatchAdmin: SupplierFilter + ExpiryStatusFilter
- QuantAdmin: batch_link (clickable)
"""

from __future__ import annotations

import logging
from datetime import date

from django.contrib import admin

logger = logging.getLogger(__name__)


# ── Fulfillment inline for OrderAdmin ────────────────────────────────


class FulfillmentOrderInline(admin.TabularInline):
    model = None  # set dynamically in _extend_order_admin
    extra = 0
    fields = ("status", "carrier", "tracking_code", "dispatched_at", "delivered_at")
    readonly_fields = ("status", "carrier", "tracking_code", "dispatched_at", "delivered_at")
    can_delete = False
    verbose_name = "fulfillment"
    verbose_name_plural = "fulfillments"

    def has_add_permission(self, request, obj=None):
        return False


def _payment_info(self, obj):
    """Show PaymentIntent info linked via order_ref."""
    from django.utils.html import format_html, format_html_join

    from shopman.payman.models import PaymentIntent

    intents = PaymentIntent.objects.filter(order_ref=obj.ref).order_by("-created_at")
    if not intents.exists():
        return "\u2014"

    rows = format_html_join(
        "",
        '<tr><td style="padding:2px 8px">{}</td>'
        '<td style="padding:2px 8px">{}</td>'
        '<td style="padding:2px 8px">{}</td>'
        '<td style="padding:2px 8px">R$ {}</td></tr>',
        (
            (
                pi.ref,
                pi.get_method_display(),
                pi.get_status_display(),
                f"{pi.amount_q / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            )
            for pi in intents
        ),
    )
    return format_html(
        '<table style="border-collapse:collapse">'
        "<thead><tr>"
        '<th style="padding:2px 8px;text-align:left">Ref</th>'
        '<th style="padding:2px 8px;text-align:left">M\u00e9todo</th>'
        '<th style="padding:2px 8px;text-align:left">Status</th>'
        '<th style="padding:2px 8px;text-align:left">Valor</th>'
        "</tr></thead><tbody>{}</tbody></table>",
        rows,
    )


_payment_info.short_description = "Pagamentos"


# ── Order admin extension ────────────────────────────────────────────


def _extend_order_admin():
    """Add Fulfillment inline and payment info to OrderAdmin."""
    from shopman.orderman.models import Fulfillment, Order

    FulfillmentOrderInline.model = Fulfillment

    try:
        OrderAdminClass = type(admin.site._registry[Order])
    except KeyError:
        return

    # Add Fulfillment inline
    existing_inlines = list(OrderAdminClass.inlines or [])
    if FulfillmentOrderInline not in existing_inlines:
        existing_inlines.append(FulfillmentOrderInline)
        OrderAdminClass.inlines = existing_inlines

    # Add payment_info readonly field
    OrderAdminClass.payment_info = _payment_info
    existing_readonly = list(OrderAdminClass.readonly_fields or [])
    if "payment_info" not in existing_readonly:
        existing_readonly.append("payment_info")
        OrderAdminClass.readonly_fields = tuple(existing_readonly)

    # Add payment_info to fieldsets (append as new tab)
    existing_fieldsets = list(OrderAdminClass.fieldsets or [])
    fieldset_names = [fs[0] for fs in existing_fieldsets]
    if "Pagamentos" not in fieldset_names:
        existing_fieldsets.append(
            ("Pagamentos", {"fields": ("payment_info",), "classes": ("tab",)})
        )
        OrderAdminClass.fieldsets = existing_fieldsets


# ── Product admin extension ──────────────────────────────────────────


def _extend_product_admin():
    """Add allows_next_day_sale checkbox to the offerman ProductAdmin."""
    from shopman.offerman.models import Product

    try:
        ProductAdminClass = type(admin.site._registry[Product])
    except KeyError:
        return

    original_get_form = ProductAdminClass.get_form

    def get_form(self, request, obj=None, **kwargs):
        form = original_get_form(request, obj, **kwargs)

        class ExtendedForm(form):
            allows_next_day_sale = __import__("django.forms", fromlist=["BooleanField"]).BooleanField(
                label="Permite venda D-1",
                required=False,
                help_text="Produto pode ser vendido no dia seguinte com desconto D-1.",
            )

            def __init__(inner_self, *args, **inner_kwargs):
                super().__init__(*args, **inner_kwargs)
                if inner_self.instance and inner_self.instance.pk:
                    inner_self.fields["allows_next_day_sale"].initial = (
                        inner_self.instance.metadata.get("allows_next_day_sale", False)
                    )

        return ExtendedForm

    def save_model(self, request, obj, form, change):
        obj.metadata["allows_next_day_sale"] = form.cleaned_data.get("allows_next_day_sale", False)
        obj.save()

    ProductAdminClass.get_form = get_form
    ProductAdminClass.save_model = save_model

    # Add allows_next_day_sale to the Configuration fieldset
    fieldsets = list(ProductAdminClass.fieldsets or [])
    for i, (title, opts) in enumerate(fieldsets):
        if title == "Configuration":
            fields = list(opts["fields"])
            if "allows_next_day_sale" not in fields:
                fields.append("allows_next_day_sale")
                fieldsets[i] = (title, {**opts, "fields": tuple(fields)})
            break
    ProductAdminClass.fieldsets = fieldsets


# ── Batch admin extension ────────────────────────────────────────────


class SupplierFilter(admin.SimpleListFilter):
    title = "fornecedor"
    parameter_name = "supplier"

    def lookups(self, request, model_admin):
        from shopman.stockman.models import Batch

        suppliers = (
            Batch.objects.exclude(supplier="")
            .values_list("supplier", flat=True)
            .distinct()
            .order_by("supplier")
        )
        return [(s, s) for s in suppliers]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(supplier=self.value())
        return queryset


class ExpiryStatusFilter(admin.SimpleListFilter):
    title = "validade"
    parameter_name = "expiry_status"

    def lookups(self, request, model_admin):
        return [
            ("expired", "Expirado"),
            ("valid", "V\u00e1lido"),
            ("no_expiry", "Sem validade"),
        ]

    def queryset(self, request, queryset):
        today = date.today()
        if self.value() == "expired":
            return queryset.filter(expiry_date__lt=today)
        if self.value() == "valid":
            return queryset.filter(expiry_date__gte=today)
        if self.value() == "no_expiry":
            return queryset.filter(expiry_date__isnull=True)
        return queryset


def _extend_batch_admin():
    """Add supplier and expiry status filters to BatchAdmin."""
    from shopman.stockman.models import Batch

    try:
        BatchAdminClass = type(admin.site._registry[Batch])
    except KeyError:
        return

    existing_filters = list(BatchAdminClass.list_filter or [])
    if SupplierFilter not in existing_filters:
        existing_filters.append(SupplierFilter)
    if ExpiryStatusFilter not in existing_filters:
        existing_filters.append(ExpiryStatusFilter)
    BatchAdminClass.list_filter = existing_filters


# ── Quant admin extension ────────────────────────────────────────────


def _extend_quant_admin():
    """Add batch link to QuantAdmin for traceability."""
    from shopman.stockman.models import Quant

    try:
        QuantAdminClass = type(admin.site._registry[Quant])
    except KeyError:
        return

    def batch_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html

        from shopman.stockman.models import Batch

        if not obj.batch:
            return "\u2014"
        batch = Batch.objects.filter(ref=obj.batch).first()
        if batch:
            url = reverse("admin:stockman_batch_change", args=[batch.pk])
            return format_html('<a href="{}">{}</a>', url, obj.batch)
        return obj.batch

    batch_link.short_description = "Lote"

    QuantAdminClass.batch_link = batch_link

    existing_display = list(QuantAdminClass.list_display or [])
    if "batch_display" in existing_display:
        idx = existing_display.index("batch_display")
        existing_display[idx] = "batch_link"
    elif "batch_link" not in existing_display:
        existing_display.append("batch_link")
    QuantAdminClass.list_display = existing_display


# ── Apply all extensions at import time ──────────────────────────────

_extend_order_admin()
_extend_product_admin()
_extend_batch_admin()
_extend_quant_admin()
