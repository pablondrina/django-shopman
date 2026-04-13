"""
SKU Validation Protocol — Interface for catalog/product validation.

Stockman defines this protocol, Offerman (or other catalog systems) implements it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SkuValidationResult:
    """Result of SKU validation."""

    valid: bool
    sku: str
    message: str | None = None
    product_name: str | None = None
    is_published: bool = True
    is_sellable: bool = True
    error_code: str | None = None  # "not_found", "unpublished", etc.


@dataclass(frozen=True)
class SkuInfo:
    """Basic SKU information."""

    sku: str
    name: str
    description: str | None
    is_published: bool
    is_sellable: bool
    unit: str  # "un", "kg", "lt", etc.
    category: str | None = None
    base_price_q: int | None = None  # In cents
    availability_policy: str = "planned_ok"
    shelflife_days: int | None = None
    metadata: dict | None = None


@dataclass(frozen=True)
class PromiseDecision:
    """Operational promise decision for a SKU in a given time scope.

    ``expected`` is cumulative: it includes what is available now
    plus what can be sustained by supply already in process before any future
    planned-only supply is considered.
    """

    approved: bool
    sku: str
    requested_qty: Decimal
    target_date: date | None
    availability_policy: str = "planned_ok"
    reason_code: str | None = None
    available_qty: Decimal = Decimal("0")
    available: Decimal = Decimal("0")
    expected: Decimal = Decimal("0")
    planned: Decimal = Decimal("0")
    is_planned: bool = False
    is_paused: bool = False


@runtime_checkable
class SkuValidator(Protocol):
    """
    Protocol for SKU validation.

    Implementations should provide methods to:
    - Validate if a SKU exists and is published in the base catalog
    - Get SKU information
    - Search SKUs for autocomplete
    """

    def validate_sku(self, sku: str) -> SkuValidationResult:
        """
        Validate if a SKU exists and is published.

        Args:
            sku: Product code

        Returns:
            SkuValidationResult with publication status and details
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
            include_inactive: Include unpublished SKUs

        Returns:
            List of SkuInfo
        """
        ...
