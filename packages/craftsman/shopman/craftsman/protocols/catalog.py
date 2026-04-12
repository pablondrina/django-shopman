"""
Catalog Protocol — interface for product/item information.

Craftsman defines these protocols, Offerman (or other catalog systems) implements them.

Two levels of abstraction:
- CatalogProtocol: Generic item resolution (any ref → ItemInfo)
- ProductInfoBackend: Product-specific queries (SKU → ProductInfo, validation)

Se não configurado: item_ref é usado como-é.
Se configurado: resolve nomes, unidades, shelf_life, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


# ══════════════════════════════════════════════════════════════
# DATA TYPES
# ══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ItemInfo:
    """Item information from catalog (generic)."""

    ref: str
    name: str
    unit: str
    category: str | None = None
    description: str | None = None
    shelf_life_days: int | None = None
    lead_time_hours: int | None = None
    is_active: bool = True
    meta: dict | None = None


@dataclass(frozen=True)
class ProductInfo:
    """Product information from catalog (product-specific)."""

    sku: str
    name: str
    description: str | None
    category: str | None
    unit: str
    base_price_q: int | None
    is_active: bool


@dataclass(frozen=True)
class SkuValidationResult:
    """SKU validation result."""

    valid: bool
    sku: str
    product_name: str | None = None
    is_active: bool = True
    error_code: str | None = None
    message: str | None = None


# ══════════════════════════════════════════════════════════════
# PROTOCOLS
# ══════════════════════════════════════════════════════════════


@runtime_checkable
class CatalogProtocol(Protocol):
    """
    Generic item resolution protocol.

    Se não configurado: item_ref é usado como-é.
    Se configurado: resolve nomes, unidades, etc.
    """

    def resolve(self, item_ref: str) -> ItemInfo | None:
        """
        Resolve an item_ref to its catalog info.

        Args:
            item_ref: Item reference string

        Returns:
            ItemInfo or None if not found
        """
        ...


@runtime_checkable
class ProductInfoBackend(Protocol):
    """
    Product-specific catalog protocol.

    Used by Offerman adapter to provide production-relevant
    product information to Craftsman.
    """

    def get_product_info(self, sku: str) -> ProductInfo | None:
        """Get product information."""
        ...

    def validate_output_sku(self, sku: str) -> SkuValidationResult:
        """Validate if SKU can be used as production output."""
        ...
