"""
Re-exports from inventory.py for convenience.

Canonical imports are from shopman.craftsman.protocols.inventory.
"""

from shopman.craftsman.protocols.inventory import (  # noqa: F401
    AvailabilityResult,
    ConsumeResult,
    InventoryProtocol,
    MaterialAdjustment,
    MaterialHold,
    MaterialNeed,
    MaterialProduced,
    MaterialStatus,
    MaterialUsed,
    ReceiveResult,
    ReleaseResult,
    ReserveResult,
)

__all__ = [
    "InventoryProtocol",
    "MaterialNeed",
    "MaterialUsed",
    "MaterialProduced",
    "MaterialStatus",
    "AvailabilityResult",
    "MaterialHold",
    "ReserveResult",
    "MaterialAdjustment",
    "ConsumeResult",
    "ReleaseResult",
    "ReceiveResult",
]
