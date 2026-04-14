"""
Craftsman Protocols.

Defines interfaces for external integrations:
- InventoryProtocol: stock management (Stockman)
- CatalogProtocol: product/item information (Offerman)
- DemandProtocol: demand history and committed orders
"""

from shopman.craftsman.protocols.catalog import (
    CatalogProtocol,
    ItemInfo,
    ProductInfo,
    ProductInfoBackend,
    SkuValidationResult,
)
from shopman.craftsman.protocols.demand import (
    DailyDemand,
    DemandProtocol,
)
from shopman.craftsman.protocols.inventory import (
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
    # Inventory Protocol
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
    # Catalog Protocol
    "CatalogProtocol",
    "ProductInfoBackend",
    "ItemInfo",
    "ProductInfo",
    "SkuValidationResult",
    # Demand Protocol
    "DemandProtocol",
    "DailyDemand",
]
