"""Orderman OrderHistoryBackend adapter."""

from django.db.models import Count, Max, Min

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
        """Return last orders for customer from Orderman."""
        from shopman.orderman.models import Order

        orders = (
            self._base_queryset(Order, customer_ref)
            .order_by("-created_at")[:limit]
        )

        return [
            OrderSummary(
                order_ref=o.ref,
                channel_ref=o.channel_ref or "",
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
        """Return aggregated order statistics from Orderman."""
        from shopman.orderman.models import Order

        qs = self._base_queryset(Order, customer_ref)

        stats = qs.aggregate(
            total_orders=Count("id"),
            first_order_at=Min("created_at"),
            last_order_at=Max("created_at"),
        )

        total_orders = stats["total_orders"] or 0

        # total_spent lives inside JSON snapshot — must iterate,
        # but we use iterator() to avoid loading all into memory
        total_spent = sum(
            (snapshot or {}).get("pricing", {}).get("total_q", 0)
            for snapshot in qs.values_list("snapshot", flat=True).iterator()
        )

        return OrderStats(
            total_orders=total_orders,
            total_spent_q=total_spent,
            first_order_at=stats["first_order_at"],
            last_order_at=stats["last_order_at"],
            average_order_q=total_spent // total_orders if total_orders > 0 else 0,
        )

    @staticmethod
    def _base_queryset(Order, customer_ref: str):
        """
        Canonical link from customer insight to orders.

        Guestman should not assume a concrete FK in Orderman. The operational
        contract today is ``order.data["customer_ref"]`` populated by the
        customer resolution service.
        """
        return Order.objects.filter(data__customer_ref=customer_ref)
