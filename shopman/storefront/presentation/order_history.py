"""Order history — storefront Presentation.

Consumes the data Projection (``shop.projections.customer``) and produces the
display shape the ``storefront/order_history.html`` template consumes: money
formatted ``R$``, status label + colour token, formatted timestamps. **No
policy** — the order list, identity resolution and status keys already arrived
sealed in the data projection.

Never imports from ``shopman.storefront.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.utils import timezone
from shopman.utils.monetary import format_money

from shopman.shop.projections import customer as customer_projection
from shopman.storefront.presentation.status import order_status_label, status_color
from shopman.storefront.presentation.types import OrderSummaryProjection

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
    """Full projection for the storefront order history page."""

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


def present_summary(summary) -> OrderSummaryProjection:
    """Render one data order summary into the display projection."""
    return OrderSummaryProjection(
        ref=summary.ref,
        created_at_display=_fmt_datetime(summary.created_at),
        total_q=summary.total_q,
        total_display=f"R$ {format_money(summary.total_q)}",
        status=summary.status,
        status_label=order_status_label(summary.status),
        status_color=status_color(summary.status),
        item_count=summary.item_count,
    )


def _fetch_orders(
    customer,
    filter_param: str,
) -> tuple[OrderSummaryProjection, ...]:
    summaries = customer_projection.history_summaries_for_customer(
        customer_ref=customer.ref,
        phone=customer.phone,
        filter_param=filter_param,
        limit=50,
    )
    return tuple(present_summary(summary) for summary in summaries)


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
    "present_summary",
]
