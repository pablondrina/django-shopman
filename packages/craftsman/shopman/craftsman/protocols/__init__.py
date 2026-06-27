"""
Craftsman Protocols.

Defines interfaces for external integrations:
- InventoryProtocol: read-only material availability (Stockman/Buyman)
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
    InventoryProtocol,
    MaterialNeed,
    MaterialStatus,
)

__all__ = [
    # Inventory Protocol (read-only availability)
    "InventoryProtocol",
    "MaterialNeed",
    "MaterialStatus",
    "AvailabilityResult",
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
