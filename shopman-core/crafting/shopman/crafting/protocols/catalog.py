"""
Catalog Protocol — interface for product/item information.

Craftsman defines this protocol, Offerman (or other catalog systems) implements it.

Se não configurado: item_ref é usado como-é.
Se configurado: resolve nomes, unidades, shelf_life, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ItemInfo:
    """Item information from catalog."""

    ref: str
    name: str
    unit: str
    category: str | None = None
    description: str | None = None
    shelf_life_days: int | None = None
    lead_time_hours: int | None = None
    is_active: bool = True
    meta: dict | None = None


# ── Backward compat aliases ──

@dataclass(frozen=True)
class ProductInfo:
    """Product information from catalog (backward compat)."""

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


@runtime_checkable
class CatalogProtocol(Protocol):
    """
    Protocol for catalog/product information.

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
    Backward compat protocol (pre-vNext).

    New code should use CatalogProtocol.
    """

    def get_product_info(self, sku: str) -> ProductInfo | None:
        """Get product information."""
        ...

    def validate_output_sku(self, sku: str) -> SkuValidationResult:
        """Validate if SKU can be used as production output."""
        ...
