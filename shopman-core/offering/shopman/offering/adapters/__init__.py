"""Offering adapters."""

from shopman.offering.adapters.catalog_backend import OfferingCatalogBackend
from shopman.offering.adapters.noop import NoopCostBackend
from shopman.offering.adapters.product_info import OfferingProductInfoBackend
from shopman.offering.adapters.sku_validator import OfferingSkuValidator

__all__ = [
    "NoopCostBackend",
    "OfferingCatalogBackend",
    "OfferingProductInfoBackend",
    "OfferingSkuValidator",
]
