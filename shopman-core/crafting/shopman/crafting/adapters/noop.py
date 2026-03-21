"""
Noop Demand Backend -- returns zero/empty for all demand queries.

Use this adapter for development or testing when a real demand source
(e.g. Omniman) is not available.

Configuration:
    CRAFTING = {
        "DEMAND_BACKEND": "shopman.crafting.adapters.noop.NoopDemandBackend",
    }
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal


class NoopDemandBackend:
    """
    No-operation implementation of the DemandProtocol.

    Returns empty history and zero committed demand for every query.
    Useful for development environments, standalone Crafting setups,
    or integration tests that should not depend on a real demand source.
    """

    def history(
        self,
        product_ref: str,
        days: int = 28,
        same_weekday: bool = True,
    ) -> list:
        """Return empty demand history."""
        return []

    def committed(self, product_ref: str, target_date: date) -> Decimal:
        """Return zero committed demand."""
        return Decimal("0")
