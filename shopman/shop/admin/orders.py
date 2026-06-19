"""Shop-level Order admin composition.

The orderman ``OrderAdmin`` lives in its own package and must not depend on
payman — Core packages are independent (no cross-package imports). The shop
orchestrator owns cross-package composition, so it subclasses the orderman
``OrderAdmin`` to surface the payment intents (payman) linked to each order.

This replaces the previous runtime ``type()`` monkey-patching of the registered
admin classes. Same-package extensions (Fulfillment inline, product D-1 flag,
batch/quant filters and links) now live in their own Core admins.
"""

from __future__ import annotations

from django.contrib import admin
from django.template.loader import render_to_string
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _
from shopman.orderman.admin import OrderAdmin as _OrdermanOrderAdmin
from shopman.orderman.models import Order


def _format_brl(amount_q: int) -> str:
    return f"{amount_q / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _order_data_rows(data: dict):
    """Curated, human-readable view of the Order.data keys an operator cares about."""
    rows: list[tuple[str, str]] = []

    def add(label, value):
        if value not in (None, "", [], {}):
            rows.append((label, value))

    fulfillment = data.get("fulfillment_type")
    add("Tipo", {"delivery": "Entrega", "pickup": "Retirada"}.get(fulfillment, fulfillment))

    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    name = customer.get("name") or ""
    phone = customer.get("phone") or ""
    add("Cliente", " · ".join(p for p in (name, phone) if p))

    add("Endereço", data.get("delivery_address"))
    date = data.get("delivery_date") or ""
    slot = data.get("delivery_time_slot") or ""
    add("Entrega em", " ".join(p for p in (date, f"({slot})" if slot else "") if p))
    if data.get("is_preorder"):
        add("Encomenda", "Sim")

    fee_q = data.get("delivery_fee_q")
    if fee_q is not None:
        add("Taxa de entrega", "Grátis" if not fee_q else f"R$ {_format_brl(int(fee_q))}")

    add("Cupom", data.get("coupon_code"))
    add("Observações", data.get("order_notes"))

    if data.get("is_gift"):
        recipient = data.get("recipient") if isinstance(data.get("recipient"), dict) else {}
        rname = recipient.get("name") or ""
        rphone = recipient.get("phone") or ""
        add("Presente para", " · ".join(p for p in (rname, rphone) if p) or "Sim")
        add("Mensagem do presente", data.get("gift_message"))
        if data.get("gift_hide_values"):
            add("Presente", "Ocultar valores na nota/etiqueta")

    return rows


admin.site.unregister(Order)


@admin.register(Order)
class OrderAdmin(_OrdermanOrderAdmin):
    """Orderman ``OrderAdmin`` plus the payment intents (payman) composition."""

    readonly_fields = _OrdermanOrderAdmin.readonly_fields + ("payment_info", "order_data_display")
    fieldsets = _OrdermanOrderAdmin.fieldsets + (
        (_("Resumo"), {"fields": ("order_data_display",), "classes": ("tab",)}),
        (_("Pagamentos"), {"fields": ("payment_info",), "classes": ("tab",)}),
    )

    @admin.display(description=_("Resumo do pedido"))
    def order_data_display(self, obj):
        rows = _order_data_rows(obj.data or {})
        if not rows:
            return "—"
        body = format_html_join(
            "",
            '<div class="flex gap-3 py-1 border-b border-base-100 dark:border-base-800">'
            '<dt class="font-medium text-base-500 dark:text-base-400 w-48 shrink-0">{}</dt>'
            '<dd class="text-sm break-words">{}</dd></div>',
            rows,
        )
        return format_html('<dl class="flex flex-col">{}</dl>', body)

    @admin.display(description=_("Pagamentos"))
    def payment_info(self, obj):
        """Show PaymentIntent rows (linked via order_ref) in an Unfold table."""
        from shopman.payman.models import PaymentIntent

        intents = PaymentIntent.objects.filter(order_ref=obj.ref).order_by("-created_at")
        if not intents.exists():
            return "—"

        table = {
            "headers": [_("Ref"), _("Método"), _("Status"), _("Valor")],
            "rows": [
                [
                    pi.ref,
                    pi.get_method_display(),
                    pi.get_status_display(),
                    f"R$ {_format_brl(pi.amount_q)}",
                ]
                for pi in intents
            ],
        }
        return render_to_string(
            "admin/shop/order_payment_info.html", {"payment_table": table}
        )
