"""
Re-exports from catalog.py for convenience.

Canonical imports are from shopman.craftsman.protocols.catalog.
"""

from shopman.craftsman.protocols.catalog import (  # noqa: F401
    CatalogProtocol,
    ItemInfo,
    ProductInfo,
    ProductInfoBackend,
    SkuValidationResult,
)

__all__ = [
    "CatalogProtocol",
    "ProductInfoBackend",
    "ItemInfo",
    "ProductInfo",
    "SkuValidationResult",
]
