"""
Demand Protocol — interface for historical demand and committed orders.

Used by craft.suggest() to calculate recommended production quantities.
Omniman (or other order management systems) implements this.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class DailyDemand:
    """Historical demand data for a single day."""

    date: date
    sold: Decimal
    wasted: Decimal
    soldout_at: time | None = None


@runtime_checkable
class DemandProtocol(Protocol):
    """
    Protocol for querying demand data.

    Se não configurado: craft.suggest() retorna [].
    Se configurado: suggest() usa history + committed para calcular sugestões.
    """

    def history(
        self,
        product_ref: str,
        days: int = 28,
        same_weekday: bool = True,
    ) -> list[DailyDemand]:
        """
        Return historical demand for a product.

        Args:
            product_ref: Product reference string
            days: Number of days to look back (default: 28)
            same_weekday: Only include same weekday as today (default: True)

        Returns:
            List of DailyDemand entries
        """
        ...

    def committed(self, product_ref: str, target_date: date) -> Decimal:
        """
        Return total committed (ordered/reserved) quantity for a date.

        Args:
            product_ref: Product reference string
            target_date: The target delivery date

        Returns:
            Total committed quantity
        """
        ...


# ── Backward compatibility ──
DemandBackend = DemandProtocol
