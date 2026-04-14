"""
Noop backends for projects that don't need advanced offering integrations.
"""

from __future__ import annotations

from decimal import Decimal

from shopman.offerman.protocols import (
    CatalogProjectionBackend,
    ContextualPrice,
    PricingBackend,
    ProjectionResult,
)
from shopman.offerman.protocols.cost import CostBackend


class NoopCostBackend:
    """CostBackend that returns None for every SKU."""

    def get_cost(self, sku: str) -> int | None:
        """Always returns None -- no cost tracking."""
        return None


class NoopPricingBackend:
    """Pricing backend that preserves the list price unchanged."""

    def get_price(
        self,
        *,
        sku: str,
        qty: Decimal,
        listing: str | None,
        list_unit_price_q: int,
        list_total_price_q: int,
        context: dict | None = None,
    ) -> ContextualPrice:
        return ContextualPrice(
            sku=sku,
            qty=qty,
            listing=listing,
            list_unit_price_q=list_unit_price_q,
            list_total_price_q=list_total_price_q,
            final_unit_price_q=list_unit_price_q,
            final_total_price_q=list_total_price_q,
            adjustments=[],
            metadata={"source": "list_price", "context": context or {}},
        )


class NoopCatalogProjectionBackend:
    """Projection backend that accepts the payload without side effects."""

    def project(self, items, *, channel: str, full_sync: bool = False) -> ProjectionResult:
        return ProjectionResult(success=True, projected=len(items), channel=channel)

    def retract(self, skus: list[str], *, channel: str) -> ProjectionResult:
        return ProjectionResult(success=True, projected=0, channel=channel)


# Verify protocol compliance at import time.
if not isinstance(NoopCostBackend(), CostBackend):
    raise TypeError("NoopCostBackend does not implement CostBackend protocol")

if not isinstance(NoopPricingBackend(), PricingBackend):
    raise TypeError("NoopPricingBackend does not implement PricingBackend protocol")

if not isinstance(NoopCatalogProjectionBackend(), CatalogProjectionBackend):
    raise TypeError("NoopCatalogProjectionBackend does not implement CatalogProjectionBackend protocol")
