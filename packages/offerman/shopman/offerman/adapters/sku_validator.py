"""
Offerman SKU Validator — Implements Stockman's SkuValidator protocol.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from shopman.stockman.protocols.sku import SkuInfo, SkuValidationResult

logger = logging.getLogger(__name__)


def _stocking_protocols_available() -> bool:
    """Check if Stockman protocols are available."""
    try:
        from shopman.stockman.protocols.sku import SkuInfo, SkuValidationResult
        return True
    except ImportError:
        return False


class OfferingSkuValidator:
    """
    SKU validator using Offerman Product model.

    Implements SkuValidator protocol from Stockman.
    """

    def validate_sku(self, sku: str):
        """Validate if SKU exists and is active."""
        from shopman.stockman.protocols.sku import SkuValidationResult
        from shopman.offerman.models import Product

        try:
            product = Product.objects.get(sku=sku)
            is_active = product.is_published and product.is_available
            return SkuValidationResult(
                valid=True,
                sku=sku,
                product_name=product.name,
                is_active=is_active,
                message=None if is_active else "Product is inactive",
            )
        except Product.DoesNotExist:
            return SkuValidationResult(
                valid=False,
                sku=sku,
                error_code="not_found",
                message=f"SKU '{sku}' not found in catalog",
            )

    def validate_skus(self, skus: list[str]) -> dict:
        """Validate multiple SKUs at once."""
        from shopman.stockman.protocols.sku import SkuValidationResult
        from shopman.offerman.models import Product

        products = Product.objects.filter(sku__in=skus)
        found = {p.sku: p for p in products}

        result = {}
        for sku in skus:
            if sku in found:
                product = found[sku]
                result[sku] = SkuValidationResult(
                    valid=True,
                    sku=sku,
                    product_name=product.name,
                    is_active=product.is_published and product.is_available,
                )
            else:
                result[sku] = SkuValidationResult(
                    valid=False,
                    sku=sku,
                    error_code="not_found",
                )

        return result

    def get_sku_info(self, sku: str):
        """Get SKU information."""
        from shopman.stockman.protocols.sku import SkuInfo
        from shopman.offerman.models import Product

        try:
            product = Product.objects.get(sku=sku)
            primary_item = product.collection_items.filter(is_primary=True).first()
            category = primary_item.collection.name if primary_item else None
            return SkuInfo(
                sku=product.sku,
                name=product.name,
                description=product.long_description,
                is_active=product.is_published and product.is_available,
                unit=product.unit,
                category=category,
                base_price_q=product.base_price_q,
            )
        except Product.DoesNotExist:
            return None

    def search_skus(
        self,
        query: str,
        limit: int = 20,
        include_inactive: bool = False,
    ) -> list:
        """Search SKUs by name or code."""
        from shopman.stockman.protocols.sku import SkuInfo
        from shopman.offerman.models import Product

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
                SkuInfo(
                    sku=p.sku,
                    name=p.name,
                    description=p.long_description,
                    is_active=p.is_published and p.is_available,
                    unit=p.unit,
                    category=category,
                    base_price_q=p.base_price_q,
                )
            )
        return result


# Singleton factory
_lock = threading.Lock()
_validator_instance: OfferingSkuValidator | None = None


def get_sku_validator() -> OfferingSkuValidator:
    """Return singleton instance of OfferingSkuValidator."""
    global _validator_instance
    if _validator_instance is None:
        with _lock:
            if _validator_instance is None:
                _validator_instance = OfferingSkuValidator()
    return _validator_instance


def reset_sku_validator() -> None:
    """Reset singleton (for tests)."""
    global _validator_instance
    _validator_instance = None
