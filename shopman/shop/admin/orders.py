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
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _
from shopman.orderman.admin import OrderAdmin as _OrdermanOrderAdmin
from shopman.orderman.models import Order


def _format_brl(amount_q: int) -> str:
    return f"{amount_q / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


admin.site.unregister(Order)


@admin.register(Order)
class OrderAdmin(_OrdermanOrderAdmin):
    """Orderman ``OrderAdmin`` plus the payment intents (payman) composition."""

    readonly_fields = _OrdermanOrderAdmin.readonly_fields + ("payment_info",)
    fieldsets = _OrdermanOrderAdmin.fieldsets + (
        (_("Pagamentos"), {"fields": ("payment_info",), "classes": ("tab",)}),
    )

    @admin.display(description=_("Pagamentos"))
    def payment_info(self, obj):
        """Show PaymentIntent rows linked via order_ref."""
        from shopman.payman.models import PaymentIntent

        intents = PaymentIntent.objects.filter(order_ref=obj.ref).order_by("-created_at")
        if not intents.exists():
            return "—"

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
                    _format_brl(pi.amount_q),
                )
                for pi in intents
            ),
        )
        return format_html(
            '<table style="border-collapse:collapse">'
            "<thead><tr>"
            '<th style="padding:2px 8px;text-align:left">Ref</th>'
            '<th style="padding:2px 8px;text-align:left">Método</th>'
            '<th style="padding:2px 8px;text-align:left">Status</th>'
            '<th style="padding:2px 8px;text-align:left">Valor</th>'
            "</tr></thead><tbody>{}</tbody></table>",
            rows,
        )
