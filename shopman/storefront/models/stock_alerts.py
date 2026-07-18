"""Alert subscriptions do cliente ("Me avise quando…").

Customer-facing: a shopper (logged-in OR anonymous with just a phone) asks to be
notified about a SKU. Dois gatilhos, um modelo:

- ``stock_back``      — o SKU esgotado voltou ao estoque
- ``production_ready`` — saiu uma fornada nova (F9 do FOMO-BROADCAST-SPECS)

O segundo não exige que o produto esteja esgotado: quem quer pão quente quer
saber da fornada, não da reposição. Ambos são idempotentes via ``notified_at``.
"""

from __future__ import annotations

from django.db import models


class StockAlertSubscription(models.Model):
    """One pending "notify me" request for a SKU.

    Anonymous subscribers carry only ``contact_phone``; authenticated ones carry
    ``customer_ref`` (and usually a phone too). A subscription is *pending* until
    ``notified_at`` is set.
    """

    class AlertType(models.TextChoices):
        STOCK_BACK = "stock_back", "voltou ao estoque"
        PRODUCTION_READY = "production_ready", "saiu do forno"

    sku = models.CharField(max_length=64, db_index=True)
    alert_type = models.CharField(
        max_length=24,
        choices=AlertType.choices,
        default=AlertType.STOCK_BACK,
    )
    channel_ref = models.CharField(max_length=32, default="web")
    customer_ref = models.CharField(max_length=64, blank=True, default="")
    contact_phone = models.CharField(max_length=32, blank=True, default="")
    subscribed_at = models.DateTimeField(auto_now_add=True)
    notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "storefront"
        verbose_name = "aviso de reposição"
        verbose_name_plural = "avisos de reposição"
        indexes = [
            models.Index(fields=["sku", "notified_at"]),
            models.Index(fields=["sku", "alert_type", "notified_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        who = self.customer_ref or self.contact_phone or "?"
        state = "pending" if self.notified_at is None else "notified"
        return f"StockAlert({self.sku}/{self.alert_type} → {who}, {state})"

    @property
    def is_pending(self) -> bool:
        return self.notified_at is None
