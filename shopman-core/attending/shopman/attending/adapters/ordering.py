"""Omniman OrderHistoryBackend adapter."""

from shopman.attending.protocols.orders import OrderHistoryBackend, OrderSummary, OrderStats


class OrderingOrderHistoryBackend:
    """
    Adapter that implements OrderHistoryBackend by querying Omniman.

    Configuration in settings.py:
        GUESTMAN = {
            "ORDER_HISTORY_BACKEND": "shopman.attending.adapters.ordering.OrderingOrderHistoryBackend",
        }
    """

    def get_customer_orders(
        self,
        customer_ref: str,
        limit: int = 10,
    ) -> list[OrderSummary]:
        """Return last orders for customer from Omniman."""
        # Late import to avoid circular dependency
        try:
            from shopman.ordering.models import Order
        except ImportError:
            return []

        orders = (
            Order.objects.filter(customer_ref=customer_ref)
            .select_related("channel")
            .order_by("-created_at")[:limit]
        )

        return [
            OrderSummary(
                order_ref=o.ref,
                channel_ref=o.channel.ref if o.channel else "",
                ordered_at=o.created_at,
                total_q=o.snapshot.get("pricing", {}).get("total_q", 0)
                if o.snapshot
                else 0,
                items_count=len(o.snapshot.get("items", [])) if o.snapshot else 0,
                status=o.status,
            )
            for o in orders
        ]

    def get_order_stats(self, customer_ref: str) -> OrderStats:
        """Return aggregated order statistics from Omniman."""
        try:
            from shopman.ordering.models import Order
            from django.db.models import Count, Min, Max
        except ImportError:
            return OrderStats(
                total_orders=0,
                total_spent_q=0,
                first_order_at=None,
                last_order_at=None,
                average_order_q=0,
            )

        qs = Order.objects.filter(customer_ref=customer_ref)

        stats = qs.aggregate(
            total_orders=Count("id"),
            first_order_at=Min("created_at"),
            last_order_at=Max("created_at"),
        )

        total_orders = stats["total_orders"] or 0

        # total_spent lives inside JSON snapshot — must iterate,
        # but we use iterator() to avoid loading all into memory
        total_spent = sum(
            o.snapshot.get("pricing", {}).get("total_q", 0)
            for o in qs.only("snapshot").iterator()
            if o.snapshot
        )

        return OrderStats(
            total_orders=total_orders,
            total_spent_q=total_spent,
            first_order_at=stats["first_order_at"],
            last_order_at=stats["last_order_at"],
            average_order_q=total_spent // total_orders if total_orders > 0 else 0,
        )
