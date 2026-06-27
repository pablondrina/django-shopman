"""
Re-exports from inventory.py for convenience.

Canonical imports are from shopman.craftsman.protocols.inventory.
"""

from shopman.craftsman.protocols.inventory import (  # noqa: F401
    AvailabilityResult,
    InventoryProtocol,
    MaterialNeed,
    MaterialStatus,
)

__all__ = [
    "InventoryProtocol",
    "MaterialNeed",
    "MaterialStatus",
    "AvailabilityResult",
]
