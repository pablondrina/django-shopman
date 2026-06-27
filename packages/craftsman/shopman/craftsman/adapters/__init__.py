"""
Craftsman Adapters (vNext).

Implementations of protocols for external systems.
Adapters use lazy imports — they only fail if you actually call them
without the required package installed.
"""

from shopman.craftsman.adapters.catalog import (
    get_catalog_backend,
    reset_catalog_backend,
)

__all__ = [
    # Offerman/Catalog adapters
    "get_catalog_backend",
    "reset_catalog_backend",
]
