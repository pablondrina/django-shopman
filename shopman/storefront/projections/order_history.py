"""OrderHistoryProjection — read model for the order history page (Fase 3).

Translates a customer's order list into an immutable projection consumed
by the ``storefront/order_history.html`` template.

``build_order_history``  → full history page projection.

Never imports from ``shopman.storefront.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.utils import timezone
from shopman.utils.monetary import format_money

from shopman.shop.projections.types import OrderSummaryProjection
from shopman.shop.services import customer_orders

logger = logging.getLogger(__name__)

FILTER_OPTIONS: tuple[tuple[str, str], ...] = (
    ("todos", "Todos"),
    ("ativos", "Ativos"),
    ("anteriores", "Anteriores"),
)


# ──────────────────────────────────────────────────────────────────────
# Dataclass
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OrderHistoryProjection:
    """Full read model for the storefront order history page."""

    orders: tuple[OrderSummaryProjection, ...]
    phone_display: str      # raw phone for |format_phone filter
    active_filter: str      # "todos" | "ativos" | "anteriores"
    filter_options: tuple[tuple[str, str], ...]
    total_count: int        # number of orders after filter applied


# ──────────────────────────────────────────────────────────────────────
# Builder
# ──────────────────────────────────────────────────────────────────────


def build_order_history(
    customer,
    *,
    filter_param: str = "todos",
) -> OrderHistoryProjection:
    """Build an ``OrderHistoryProjection`` for the given customer.

    Always returns a projection. Service failures degrade to empty list.
    """
    orders = _fetch_orders(customer, filter_param)
    return OrderHistoryProjection(
        orders=orders,
        phone_display=customer.phone or "",
        active_filter=filter_param if filter_param in {f for f, _ in FILTER_OPTIONS} else "todos",
        filter_options=FILTER_OPTIONS,
        total_count=len(orders),
    )


# ──────────────────────────────────────────────────────────────────────
# Internals
# ──────────────────────────────────────────────────────────────────────


def _fetch_orders(
    customer,
    filter_param: str,
) -> tuple[OrderSummaryProjection, ...]:
    summaries = customer_orders.history_summaries_for_phone(
        customer.phone,
        filter_param=filter_param,
        limit=50,
    )
    return tuple(
        OrderSummaryProjection(
            ref=order.ref,
            created_at_display=_fmt_datetime(order.created_at),
            total_q=order.total_q,
            total_display=f"R$ {format_money(order.total_q)}",
            status=order.status,
            status_label=order.status_label,
            status_color=order.status_color,
            item_count=order.item_count,
        )
        for order in summaries
    )


def _fmt_datetime(dt) -> str:
    """Format a datetime as 'DD/MM/AAAA às HH:MM'."""
    try:
        local = timezone.localtime(dt)
        return local.strftime("%d/%m/%Y às %H:%M")
    except Exception:
        logger.debug("order_history_projection_datetime_format_failed dt=%r", dt, exc_info=True)
        return str(dt)


__all__ = [
    "FILTER_OPTIONS",
    "OrderHistoryProjection",
    "build_order_history",
]
