"""Customer order history contract exposed by Orderman."""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Count, Max, Min
from shopman.orderman.models import Order


@dataclass(frozen=True)
class CustomerOrderRecord:
    """Sealed summary of a customer's order."""

    order_ref: str
    channel_ref: str
    ordered_at: object
    total_q: int
    items_count: int
    status: str
    items: list[dict]


@dataclass(frozen=True)
class CustomerOrderStats:
    """Aggregated customer order metrics."""

    total_orders: int
    total_spent_q: int
    first_order_at: object | None
    last_order_at: object | None
    average_order_q: int


class CustomerOrderHistoryService:
    """
    Public read contract from Orderman to identity/CRM consumers.

    The canonical link is ``order.data["customer_ref"]`` sealed by the
    customer resolution flow in the framework.
    """

    @classmethod
    def list_customer_orders(
        cls,
        customer_ref: str,
        *,
        limit: int = 10,
    ) -> list[CustomerOrderRecord]:
        orders = cls._base_queryset(customer_ref).order_by("-created_at")[:limit]
        return [
            CustomerOrderRecord(
                order_ref=order.ref,
                channel_ref=order.channel_ref or "",
                ordered_at=order.created_at,
                total_q=(order.snapshot or {}).get("pricing", {}).get(
                    "total_q",
                    order.total_q,
                ),
                items_count=len((order.snapshot or {}).get("items", [])),
                status=order.status,
                items=list((order.snapshot or {}).get("items", [])),
            )
            for order in orders
        ]

    @classmethod
    def get_customer_stats(cls, customer_ref: str) -> CustomerOrderStats:
        qs = cls._base_queryset(customer_ref)
        stats = qs.aggregate(
            total_orders=Count("id"),
            first_order_at=Min("created_at"),
            last_order_at=Max("created_at"),
        )

        total_orders = stats["total_orders"] or 0
        total_spent_q = sum(
            (snapshot or {}).get("pricing", {}).get("total_q", 0)
            for snapshot in qs.values_list("snapshot", flat=True).iterator()
        )

        return CustomerOrderStats(
            total_orders=total_orders,
            total_spent_q=total_spent_q,
            first_order_at=stats["first_order_at"],
            last_order_at=stats["last_order_at"],
            average_order_q=total_spent_q // total_orders if total_orders > 0 else 0,
        )

    @staticmethod
    def _base_queryset(customer_ref: str):
        return Order.objects.filter(data__customer_ref=customer_ref)
