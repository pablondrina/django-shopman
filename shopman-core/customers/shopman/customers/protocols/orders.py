"""Order history protocol for cross-app communication."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class OrderSummary:
    """Summary of a single order."""

    order_ref: str
    channel_ref: str
    ordered_at: datetime
    total_q: int  # centavos
    items_count: int
    status: str


@dataclass(frozen=True)
class OrderStats:
    """Aggregated order statistics for a customer."""

    total_orders: int
    total_spent_q: int  # centavos
    first_order_at: datetime | None
    last_order_at: datetime | None
    average_order_q: int  # centavos


@runtime_checkable
class OrderHistoryBackend(Protocol):
    """
    Protocol for accessing order history.

    Used by contrib/insights to calculate RFM and metrics.
    Implemented by adapters/ordering.py.

    Configuration in settings.py:
        GUESTMAN = {
            "ORDER_HISTORY_BACKEND": "shopman.customers.adapters.ordering.OrderingOrderHistoryBackend",
        }
    """

    def get_customer_orders(
        self,
        customer_ref: str,
        limit: int = 10,
    ) -> list[OrderSummary]:
        """
        Return last orders for customer.

        Args:
            customer_ref: Customer ref
            limit: Maximum orders to return

        Returns:
            List of OrderSummary ordered by date (most recent first)
        """
        ...

    def get_order_stats(
        self,
        customer_ref: str,
    ) -> OrderStats:
        """
        Return aggregated order statistics.

        Args:
            customer_ref: Customer ref

        Returns:
            OrderStats with totals and averages
        """
        ...
