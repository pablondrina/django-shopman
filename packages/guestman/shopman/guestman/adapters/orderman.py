"""Orderman OrderHistoryBackend adapter."""

from shopman.guestman.protocols.orders import OrderHistoryBackend, OrderSummary, OrderStats


class OrdermanOrderHistoryBackend:
    """
    Adapter that implements OrderHistoryBackend by querying Orderman.

    Configuration in settings.py:
        GUESTMAN = {
            "ORDER_HISTORY_BACKEND": "shopman.guestman.adapters.orderman.OrdermanOrderHistoryBackend",
        }
    """

    def get_customer_orders(
        self,
        customer_ref: str,
        limit: int = 10,
    ) -> list[OrderSummary]:
        """Return last orders for customer from Orderman's public history contract."""
        from shopman.orderman.services import CustomerOrderHistoryService

        orders = CustomerOrderHistoryService.list_customer_orders(
            customer_ref,
            limit=limit,
        )

        return [
            OrderSummary(
                order_ref=o.order_ref,
                channel_ref=o.channel_ref,
                ordered_at=o.ordered_at,
                total_q=o.total_q,
                items_count=o.items_count,
                status=o.status,
            )
            for o in orders
        ]

    def get_order_stats(self, customer_ref: str) -> OrderStats:
        """Return aggregated order statistics from Orderman's public history contract."""
        from shopman.orderman.services import CustomerOrderHistoryService

        stats = CustomerOrderHistoryService.get_customer_stats(customer_ref)

        return OrderStats(
            total_orders=stats.total_orders,
            total_spent_q=stats.total_spent_q,
            first_order_at=stats.first_order_at,
            last_order_at=stats.last_order_at,
            average_order_q=stats.average_order_q,
        )
