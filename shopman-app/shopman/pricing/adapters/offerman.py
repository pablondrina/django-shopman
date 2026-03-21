"""
Shopman Offerman Pricing Adapter — Adapter para precificação via Offerman.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


def _offerman_available() -> bool:
    """Check if Offerman is installed."""
    try:
        from shopman.offering import CatalogService
        return True
    except ImportError:
        return False


class OffermanPricingBackend:
    """
    Adapter que conecta pricing ao Offerman.
    """

    def get_price(self, sku: str, channel: Any) -> int | None:
        if not _offerman_available():
            logger.warning("get_price: Offerman not installed")
            return None

        from shopman.offering import CatalogService

        try:
            channel_ref = getattr(channel, "ref", None) if channel else None
            price_q = CatalogService.price(sku, Decimal("1"), channel=channel_ref)
            return price_q
        except Exception as e:
            logger.warning("get_price: Failed for SKU %s: %s", sku, e)
            return None


class OffermanCatalogBackend:
    """
    Adapter completo para catálogo via Offerman.
    """

    def get_product(self, sku: str):
        if not _offerman_available():
            logger.warning("get_product: Offerman not installed")
            return None

        from shopman.offering import CatalogService

        try:
            return CatalogService.get(sku)
        except Exception as e:
            logger.debug("get_product: Failed for SKU %s: %s", sku, e)
            return None

    def get_price(
        self,
        sku: str,
        qty: Decimal = Decimal("1"),
        channel: str | None = None,
    ) -> int:
        if not _offerman_available():
            raise ImportError("Offerman is not installed")

        from shopman.offering import CatalogService

        return CatalogService.price(sku, qty, channel=channel)

    def validate_sku(self, sku: str):
        if not _offerman_available():
            raise ImportError("Offerman is not installed")

        from shopman.offering import CatalogService

        return CatalogService.validate(sku)

    def expand_bundle(self, sku: str, qty: Decimal = Decimal("1")):
        if not _offerman_available():
            return []

        from shopman.offering import CatalogService

        try:
            return CatalogService.expand(sku, qty)
        except Exception:
            logger.warning("expand_bundle failed for SKU %s", sku, exc_info=True)
            return []

    def is_bundle(self, sku: str) -> bool:
        if not _offerman_available():
            return False

        from shopman.offering import CatalogService

        try:
            product = CatalogService.get(sku)
            return product.is_bundle if product else False
        except Exception:
            logger.warning("is_bundle check failed for SKU %s", sku, exc_info=True)
            return False

    def search_products(
        self,
        query: str | None = None,
        category: str | None = None,
        collection: str | None = None,
        limit: int = 20,
    ):
        if not _offerman_available():
            return []

        from shopman.offering import CatalogService

        try:
            return CatalogService.search(
                query=query,
                category=category,
                collection=collection,
                limit=limit,
            )
        except Exception as e:
            logger.warning("search_products: Failed: %s", e)
            return []
