"""Customer favorites — the explicit "coleção dinâmica do cliente".

A heart toggle on the PDP/cards. Favorites is a customer-scoped collection (vs the
global dynamic collections featured/fresh_from_oven/new_arrivals), so it lives on
the account axis, not the channel registry. Loose coupling to Guestman via ref.
"""

from __future__ import annotations

from django.db import models


class CustomerFavorite(models.Model):
    customer_ref = models.CharField(max_length=64, db_index=True)
    sku = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "storefront"
        constraints = [
            models.UniqueConstraint(
                fields=["customer_ref", "sku"], name="uniq_customer_favorite"
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        return f"CustomerFavorite({self.customer_ref} ♥ {self.sku})"
