"""
Backward compatibility — re-exports from inventory.py.

New code should import from shopman.craftsman.protocols.inventory.
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
    StockBackend,
)

__all__ = [
    "StockBackend",
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
