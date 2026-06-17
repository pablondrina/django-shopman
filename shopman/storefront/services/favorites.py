"""Customer favorites service — add/remove/toggle/list (per customer).

Favorites is the customer-scoped dynamic collection ("Seus favoritos"). Resolved
on the account axis (not the global channel registry). Surfaces compose catalog
cards from ``skus_for()`` via the catalog presentation.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def add(customer_ref: str, sku: str) -> bool:
    """Mark a SKU as favorite. Idempotent. Returns True (is favorite)."""
    from shopman.storefront.models import CustomerFavorite

    if not customer_ref or not sku:
        return False
    CustomerFavorite.objects.get_or_create(customer_ref=customer_ref, sku=sku)
    return True


def remove(customer_ref: str, sku: str) -> bool:
    """Unfavorite a SKU. Idempotent. Returns False (not favorite)."""
    from shopman.storefront.models import CustomerFavorite

    if customer_ref and sku:
        CustomerFavorite.objects.filter(customer_ref=customer_ref, sku=sku).delete()
    return False


def toggle(customer_ref: str, sku: str) -> bool:
    """Flip favorite state. Returns the new state (True = now favorite)."""
    from shopman.storefront.models import CustomerFavorite

    if not customer_ref or not sku:
        return False
    existing = CustomerFavorite.objects.filter(customer_ref=customer_ref, sku=sku).first()
    if existing:
        existing.delete()
        return False
    CustomerFavorite.objects.create(customer_ref=customer_ref, sku=sku)
    return True


def skus_for(customer_ref: str) -> list[str]:
    """Favorite SKUs for a customer, most-recent first."""
    from shopman.storefront.models import CustomerFavorite

    if not customer_ref:
        return []
    return list(
        CustomerFavorite.objects.filter(customer_ref=customer_ref).values_list("sku", flat=True)
    )


def favorite_sku_set(customer_ref: str) -> set[str]:
    """Set form for cheap membership checks (heart state on cards/PDP)."""
    return set(skus_for(customer_ref))
