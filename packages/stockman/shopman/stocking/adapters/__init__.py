"""
Stocking Adapters.

Implementations of protocols for external systems.
"""

from shopman.stocking.adapters.crafting import CraftingBackend, get_production_backend
from shopman.stocking.adapters.noop import NoopSkuValidator
from shopman.stocking.adapters.offering import (
    get_sku_validator,
    reset_sku_validator,
)

__all__ = [
    "CraftingBackend",
    "NoopSkuValidator",
    "get_production_backend",
    "get_sku_validator",
    "reset_sku_validator",
]
