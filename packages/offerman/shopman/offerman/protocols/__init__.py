"""Offerman protocols."""

from shopman.offerman.protocols.catalog import (
    CatalogBackend,
    ProductInfo,
    PriceInfo,
    SkuValidation,
    BundleComponent,
)
from shopman.offerman.protocols.cost import CostBackend
from shopman.offerman.protocols.projection import (
    CatalogProjectionBackend,
    ProjectedItem,
    ProjectionResult,
)

__all__ = [
    "CatalogBackend",
    "CatalogProjectionBackend",
    "CostBackend",
    "ProductInfo",
    "PriceInfo",
    "ProjectedItem",
    "ProjectionResult",
    "SkuValidation",
    "BundleComponent",
]
