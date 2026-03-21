"""
Backward compatibility — re-exports from catalog.py.

New code should import from shopman.crafting.protocols.catalog.
"""

from shopman.crafting.protocols.catalog import (  # noqa: F401
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
