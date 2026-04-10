"""
SKU Validation Protocol — Interface for catalog/product validation.

Stockman defines this protocol, Offerman (or other catalog systems) implements it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SkuValidationResult:
    """Result of SKU validation."""

    valid: bool
    sku: str
    message: str | None = None
    product_name: str | None = None
    is_active: bool = True
    error_code: str | None = None  # "not_found", "inactive", etc.


@dataclass(frozen=True)
class SkuInfo:
    """Basic SKU information."""

    sku: str
    name: str
    description: str | None
    is_active: bool
    unit: str  # "un", "kg", "lt", etc.
    category: str | None = None
    base_price_q: int | None = None  # In cents
    metadata: dict | None = None


@runtime_checkable
class SkuValidator(Protocol):
    """
    Protocol for SKU validation.

    Implementations should provide methods to:
    - Validate if a SKU exists and is active
    - Get SKU information
    - Search SKUs for autocomplete
    """

    def validate_sku(self, sku: str) -> SkuValidationResult:
        """
        Validate if a SKU exists and is active.

        Args:
            sku: Product code

        Returns:
            SkuValidationResult with status and details
        """
        ...

    def validate_skus(self, skus: list[str]) -> dict[str, SkuValidationResult]:
        """
        Validate multiple SKUs at once.

        Args:
            skus: List of product codes

        Returns:
            Dict[sku, SkuValidationResult]
        """
        ...

    def get_sku_info(self, sku: str) -> SkuInfo | None:
        """
        Get SKU information.

        Args:
            sku: Product code

        Returns:
            SkuInfo or None if not found
        """
        ...

    def search_skus(
        self,
        query: str,
        limit: int = 20,
        include_inactive: bool = False,
    ) -> list[SkuInfo]:
        """
        Search SKUs by name or code.

        Args:
            query: Search term
            limit: Maximum results
            include_inactive: Include inactive SKUs

        Returns:
            List of SkuInfo
        """
        ...
