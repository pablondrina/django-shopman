"""
Crafting Protocols (vNext).

Defines interfaces for external integrations:
- InventoryProtocol: stock management (Stocking)
- CatalogProtocol: product/item information (Offering)
- DemandProtocol: demand history and committed orders (Omniman)
"""

from shopman.crafting.protocols.inventory import (
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
from shopman.crafting.protocols.catalog import (
    CatalogProtocol,
    ItemInfo,
    ProductInfo,
    ProductInfoBackend,
    SkuValidationResult,
)
from shopman.crafting.protocols.demand import (
    DailyDemand,
    DemandBackend,
    DemandProtocol,
)

__all__ = [
    # Inventory Protocol
    "InventoryProtocol",
    "StockBackend",
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
    "DemandBackend",
    "DailyDemand",
]
