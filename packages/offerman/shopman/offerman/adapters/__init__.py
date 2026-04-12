"""Offerman adapters."""

from shopman.offerman.adapters.catalog_backend import OffermanCatalogBackend
from shopman.offerman.adapters.noop import NoopCostBackend
from shopman.offerman.adapters.product_info import ProductInfoBackend
from shopman.offerman.adapters.sku_validator import SkuValidator

__all__ = [
    "NoopCostBackend",
    "OffermanCatalogBackend",
    "ProductInfoBackend",
    "SkuValidator",
]
