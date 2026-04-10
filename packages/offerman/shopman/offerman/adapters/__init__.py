"""Offerman adapters."""

from shopman.offerman.adapters.catalog_backend import CatalogBackend
from shopman.offerman.adapters.noop import NoopCostBackend
from shopman.offerman.adapters.product_info import ProductInfoBackend
from shopman.offerman.adapters.sku_validator import SkuValidator

__all__ = [
    "NoopCostBackend",
    "CatalogBackend",
    "ProductInfoBackend",
    "SkuValidator",
]
