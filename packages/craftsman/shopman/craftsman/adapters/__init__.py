"""
Crafting Adapters (vNext).

Implementations of protocols for external systems.
Adapters use lazy imports — they only fail if you actually call them
without the required package installed.
"""

from shopman.craftsman.adapters.stocking import StockingBackend, get_stock_backend
from shopman.craftsman.adapters.offering import (
    get_catalog_backend,
    get_product_info_backend,
    reset_catalog_backend,
    reset_product_info_backend,
)

__all__ = [
    # Stocking adapters
    "StockingBackend",
    "get_stock_backend",
    # Offering/Catalog adapters
    "get_catalog_backend",
    "get_product_info_backend",
    "reset_catalog_backend",
    "reset_product_info_backend",
]
