"""
Pricing backend — ponte para shopman.offering.

Inclui OfferingBackend (cascata de preço) e SimplePricingBackend.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


def _offering_available() -> bool:
    try:
        from shopman.offering import CatalogService  # noqa: F401

        return True
    except ImportError:
        return False


class OfferingBackend:
    """Resolve preço pela cascata: grupo do cliente → listing do canal → preço base."""

    def get_price(self, sku: str, channel: Any, customer=None, qty: int = 1) -> int | None:
        if not _offering_available():
            return None

        # 1. Preço do grupo do cliente (se identificado e tem grupo com listing)
        if customer and hasattr(customer, "group") and customer.group:
            listing_ref = getattr(customer.group, "listing_ref", None)
            if listing_ref:
                item = self._get_listing_item(listing_ref, sku, qty=qty)
                if item and item.is_available:
                    return item.price_q

        # 2. Preço do canal (via listing do canal)
        channel_listing = getattr(channel, "listing_ref", None) if channel else None
        if channel_listing:
            item = self._get_listing_item(channel_listing, sku, qty=qty)
            if item and item.is_available:
                return item.price_q

        # 3. Preço base do produto
        try:
            from shopman.offering.models import Product

            product = Product.objects.get(sku=sku)
            return product.base_price_q
        except Exception:
            return None

    def _get_listing_item(self, listing_ref, sku, qty=1):
        """Find the ListingItem with the highest min_qty tier <= qty."""
        try:
            from shopman.offering.models import ListingItem

            return (
                ListingItem.objects.filter(
                    listing__ref=listing_ref,
                    product__sku=sku,
                    min_qty__lte=qty,
                    is_published=True,
                )
                .order_by("-min_qty")
                .first()
            )
        except Exception:
            return None


class SimplePricingBackend:
    """Pricing backend simples — lê Product.base_price_q diretamente."""

    def __init__(self, product_resolver=None):
        self._resolver = product_resolver

    def get_price(self, sku: str, channel: Any) -> int | None:
        try:
            if self._resolver:
                product = self._resolver(sku)
            else:
                from shopman.offering.models import Product

                product = Product.objects.get(sku=sku)
            return product.base_price_q
        except Exception:
            return None


class ChannelPricingBackend:
    """Pricing backend por canal — busca listing, fallback para base_price_q."""

    def __init__(self, product_resolver=None, listing_resolver=None):
        self._product_resolver = product_resolver
        self._listing_resolver = listing_resolver

    def get_price(self, sku: str, channel: Any) -> int | None:
        if self._listing_resolver:
            try:
                listing = self._listing_resolver(sku, channel.ref)
                if hasattr(listing, "price_q") and listing.price_q is not None:
                    return listing.price_q
            except Exception:
                pass

        try:
            if self._product_resolver:
                product = self._product_resolver(sku)
            else:
                from shopman.offering.models import Product

                product = Product.objects.get(sku=sku)
            return product.base_price_q
        except Exception:
            return None


class CatalogPricingBackend:
    """Adapter que conecta pricing ao Offering CatalogService.

    Returns the per-unit price for the applicable min_qty tier.
    Uses CatalogService.unit_price() so the modifier receives the
    correct unit price (not qty * unit).
    """

    def get_price(self, sku: str, channel: Any, qty: int = 1) -> int | None:
        if not _offering_available():
            return None

        from shopman.offering import CatalogService

        try:
            channel_ref = getattr(channel, "ref", None) if channel else None
            return CatalogService.unit_price(sku, Decimal(str(qty)), channel=channel_ref)
        except Exception:
            return None


__all__ = ["OfferingBackend", "SimplePricingBackend", "ChannelPricingBackend", "CatalogPricingBackend"]
