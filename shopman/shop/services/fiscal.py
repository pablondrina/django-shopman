"""
Fiscal (NFC-e) service.

ASYNC — creates Directives for later processing.
Smart no-op when fiscal_pool is empty (no backend configured).
"""

from __future__ import annotations

import logging

from shopman.shop import directives
from shopman.shop.fiscal import fiscal_pool
from shopman.shop.directives import FISCAL_CANCEL_NFCE, FISCAL_EMIT_NFCE

logger = logging.getLogger(__name__)


def emit(order) -> None:
    """
    Schedule NFC-e emission for the order.

    Smart no-op if no fiscal backend is configured.
    Creates a Directive with topic FISCAL_EMIT_NFCE.

    ASYNC — retry-safe.
    """
    if not fiscal_pool.get_backend():
        return

    if (order.data or {}).get("nfce_access_key"):
        return

    directives.queue(
        FISCAL_EMIT_NFCE, order,
        items=_build_fiscal_items(order),
        payment=(order.data or {}).get("payment", {}),
        customer=(order.data or {}).get("customer", {}),
    )

    logger.info("fiscal.emit: queued for order %s", order.ref)


def cancel(order) -> None:
    """
    Schedule NFC-e cancellation for the order.

    Smart no-op if no fiscal backend is configured or NFC-e was never emitted.
    Creates a Directive with topic FISCAL_CANCEL_NFCE.

    ASYNC — retry-safe.
    """
    if not fiscal_pool.get_backend():
        return

    if not (order.data or {}).get("nfce_access_key"):
        return

    if (order.data or {}).get("nfce_cancelled"):
        return

    directives.queue(
        FISCAL_CANCEL_NFCE, order,
        reason=(order.data or {}).get("cancellation_reason", "cancelled"),
    )

    logger.info("fiscal.cancel: queued for order %s", order.ref)


def _build_fiscal_items(order) -> list[dict]:
    """Build item list for fiscal emission from order items."""
    items = []
    for item in order.items.all():
        items.append({
            "sku": item.sku,
            "name": item.name,
            "qty": float(item.qty),
            "unit_price_q": item.unit_price_q,
            "total_q": item.line_total_q,
        })
    return items
