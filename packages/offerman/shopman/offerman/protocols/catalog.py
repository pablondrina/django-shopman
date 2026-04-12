"""Catalog protocols."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ProductInfo:
    """Product information.

    Commercial state is determined by two flags:
    - is_published: Published in catalog (False = hidden/discontinued)
    - is_sellable: Can be purchased strategically (False = ingredient or paused)
    """

    sku: str
    name: str
    description: str | None
    category: str | None
    unit: str
    is_bundle: bool
    base_price_q: int
    is_published: bool = True
    is_sellable: bool = True
    keywords: list[str] | None = None


@dataclass(frozen=True)
class PriceInfo:
    """Price information."""

    sku: str
    unit_price_q: int
    total_price_q: int
    qty: Decimal
    listing: str | None = None


@dataclass(frozen=True)
class SkuValidation:
    """Validation result.

    Commercial state is determined by two flags:
    - is_published: Published in catalog
    - is_sellable: Can be purchased strategically
    """

    valid: bool
    sku: str
    name: str | None = None
    is_published: bool = True
    is_sellable: bool = True
    error_code: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class BundleComponent:
    """Bundle component."""

    sku: str
    name: str
    qty: Decimal


@runtime_checkable
class CatalogBackend(Protocol):
    """Interface for catalog queries."""

    def get_product(self, sku: str) -> ProductInfo | None:
        """Return product by SKU."""
        ...

    def get_price(
        self,
        sku: str,
        qty: Decimal = Decimal("1"),
        channel: str | None = None,
    ) -> PriceInfo:
        """Return price."""
        ...

    def validate_sku(self, sku: str) -> SkuValidation:
        """Validate SKU."""
        ...

    def expand_bundle(
        self, sku: str, qty: Decimal = Decimal("1")
    ) -> list[BundleComponent]:
        """Expand bundle."""
        ...
