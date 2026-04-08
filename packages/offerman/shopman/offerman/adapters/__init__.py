"""Offering adapters."""

from shopman.offerman.adapters.catalog_backend import OfferingCatalogBackend
from shopman.offerman.adapters.noop import NoopCostBackend
from shopman.offerman.adapters.product_info import OfferingProductInfoBackend
from shopman.offerman.adapters.sku_validator import OfferingSkuValidator

__all__ = [
    "NoopCostBackend",
    "OfferingCatalogBackend",
    "OfferingProductInfoBackend",
    "OfferingSkuValidator",
]
