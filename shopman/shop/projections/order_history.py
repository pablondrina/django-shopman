"""OrderHistoryProjection — read model for the order history page (Fase 3).

Translates a customer's order list into an immutable projection consumed
by the ``storefront/order_history.html`` template.

``build_order_history``  → full history page projection.

Never imports from ``shopman.shop.web.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.utils import timezone
from shopman.utils.monetary import format_money

from .types import (
    ORDER_STATUS_COLORS,
    ORDER_STATUS_LABELS_PT,
    OrderSummaryProjection,
)

if TYPE_CHECKING:
    from shopman.guestman.models import Customer

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = frozenset({"new", "confirmed", "preparing", "ready", "dispatched"})

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
    customer: Customer,
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
    customer: Customer,
    filter_param: str,
) -> tuple[OrderSummaryProjection, ...]:
    try:
        from shopman.orderman.models import Order

        qs = Order.objects.filter(
            handle_type="phone",
            handle_ref=customer.phone,
        ).order_by("-created_at")

        if filter_param == "ativos":
            qs = qs.filter(status__in=_ACTIVE_STATUSES)
        elif filter_param == "anteriores":
            qs = qs.exclude(status__in=_ACTIVE_STATUSES)

        return tuple(
            OrderSummaryProjection(
                ref=order.ref,
                created_at_display=_fmt_datetime(order.created_at),
                total_q=order.total_q,
                total_display=f"R$ {format_money(order.total_q)}",
                status=order.status,
                status_label=ORDER_STATUS_LABELS_PT.get(order.status, order.status),
                status_color=ORDER_STATUS_COLORS.get(
                    order.status,
                    "bg-surface-alt text-on-surface/60 border border-outline",
                ),
                item_count=order.items.count(),
            )
            for order in qs[:50]
        )
    except Exception:
        logger.exception(
            "order_history_projection_failed customer=%s", customer.ref
        )
        return ()


def _fmt_datetime(dt) -> str:
    """Format a datetime as 'DD/MM/AAAA às HH:MM'."""
    try:
        local = timezone.localtime(dt)
        return local.strftime("%d/%m/%Y às %H:%M")
    except Exception:
        return str(dt)


__all__ = [
    "FILTER_OPTIONS",
    "OrderHistoryProjection",
    "build_order_history",
]
