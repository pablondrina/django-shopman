"""Stock-back alert subscriptions ("Me avise quando disponível").

Customer-facing: a shopper (logged-in OR anonymous with just a phone) asks to be
notified when a truly-out-of-stock SKU comes back. Fired by a stock-arrival
receiver (storefront.handlers) — idempotent via ``notified_at``.
"""

from __future__ import annotations

from django.db import models


class StockAlertSubscription(models.Model):
    """One pending "notify me when back" request for a SKU.

    Anonymous subscribers carry only ``contact_phone``; authenticated ones carry
    ``customer_ref`` (and usually a phone too). A subscription is *pending* until
    ``notified_at`` is set.
    """

    sku = models.CharField(max_length=64, db_index=True)
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
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        who = self.customer_ref or self.contact_phone or "?"
        state = "pending" if self.notified_at is None else "notified"
        return f"StockAlert({self.sku} → {who}, {state})"

    @property
    def is_pending(self) -> bool:
        return self.notified_at is None
