"""
Offerman Product Info Adapter — Implements Craftsman's ProductInfoBackend protocol.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shopman.craftsman.protocols.catalog import ProductInfo, SkuValidationResult

logger = logging.getLogger(__name__)


def _crafting_protocols_available() -> bool:
    """Check if Craftsman protocols are available."""
    try:
        from shopman.craftsman.protocols.catalog import ProductInfo, SkuValidationResult
        return True
    except ImportError:
        return False


class OfferingProductInfoBackend:
    """
    Product info backend using Offerman Product model.

    Implements ProductInfoBackend protocol from Craftsman.
    """

    def get_product_info(self, sku: str):
        """Get product information."""
        from shopman.craftsman.protocols.catalog import ProductInfo
        from shopman.offerman.models import Product

        try:
            product = Product.objects.get(sku=sku)
            primary_item = product.collection_items.filter(is_primary=True).first()
            category = primary_item.collection.name if primary_item else None
            return ProductInfo(
                sku=product.sku,
                name=product.name,
                description=product.long_description,
                category=category,
                unit=product.unit,
                base_price_q=product.base_price_q,
                is_active=product.is_published and product.is_available,
            )
        except Product.DoesNotExist:
            return None

    def validate_output_sku(self, sku: str):
        """Validate if SKU can be used as production output."""
        from shopman.craftsman.protocols.catalog import SkuValidationResult
        from shopman.offerman.models import Product

        try:
            product = Product.objects.get(sku=sku)

            if product.is_bundle:
                return SkuValidationResult(
                    valid=False,
                    sku=sku,
                    error_code="is_bundle",
                    message="Cannot use bundle as production output",
                )

            return SkuValidationResult(
                valid=True,
                sku=sku,
                product_name=product.name,
                is_active=product.is_published and product.is_available,
            )

        except Product.DoesNotExist:
            return SkuValidationResult(
                valid=True,
                sku=sku,
                message="SKU not found, will be created on first production",
            )

    def get_product_infos(self, skus: list[str]) -> dict:
        """Get product information for multiple SKUs."""
        from shopman.craftsman.protocols.catalog import ProductInfo
        from shopman.offerman.models import Product

        products = Product.objects.filter(sku__in=skus).prefetch_related(
            "collection_items__collection"
        )
        found = {p.sku: p for p in products}

        result = {}
        for sku in skus:
            if sku in found:
                p = found[sku]
                primary_item = p.collection_items.filter(is_primary=True).first()
                category = primary_item.collection.name if primary_item else None
                result[sku] = ProductInfo(
                    sku=p.sku,
                    name=p.name,
                    description=p.long_description,
                    category=category,
                    unit=p.unit,
                    base_price_q=p.base_price_q,
                    is_active=p.is_published and p.is_available,
                )
            else:
                result[sku] = None

        return result

    def search_products(
        self,
        query: str,
        limit: int = 20,
        include_inactive: bool = False,
    ) -> list:
        """Search products by name or SKU."""
        from shopman.craftsman.protocols.catalog import ProductInfo
        from shopman.offerman.models import Product
        from django.db import models

        qs = Product.objects.filter(
            models.Q(sku__icontains=query) | models.Q(name__icontains=query)
        ).prefetch_related("collection_items__collection")

        if not include_inactive:
            qs = qs.filter(is_published=True, is_available=True)

        qs = qs[:limit]

        result = []
        for p in qs:
            primary_item = p.collection_items.filter(is_primary=True).first()
            category = primary_item.collection.name if primary_item else None
            result.append(
                ProductInfo(
                    sku=p.sku,
                    name=p.name,
                    description=p.long_description,
                    category=category,
                    unit=p.unit,
                    base_price_q=p.base_price_q,
                    is_active=p.is_published and p.is_available,
                )
            )
        return result


# Singleton factory
_lock = threading.Lock()
_backend_instance: OfferingProductInfoBackend | None = None


def get_product_info_backend() -> OfferingProductInfoBackend:
    """Return singleton instance of OfferingProductInfoBackend."""
    global _backend_instance
    if _backend_instance is None:
        with _lock:
            if _backend_instance is None:
                _backend_instance = OfferingProductInfoBackend()
    return _backend_instance


def reset_product_info_backend() -> None:
    """Reset singleton (for tests)."""
    global _backend_instance
    _backend_instance = None
