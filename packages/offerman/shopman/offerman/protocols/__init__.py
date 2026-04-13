"""Offerman protocols."""

from shopman.offerman.protocols.catalog import (
    CatalogBackend,
    PricingBackend,
    ContextualPrice,
    PriceAdjustment,
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
    "ContextualPrice",
    "PricingBackend",
    "CostBackend",
    "PriceAdjustment",
    "ProductInfo",
    "PriceInfo",
    "ProjectedItem",
    "ProjectionResult",
    "SkuValidation",
    "BundleComponent",
]
