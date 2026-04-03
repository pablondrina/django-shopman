"""
Fiscal (NFC-e) service.

Adapter: get_adapter("fiscal") → fiscal_focus / fiscal_mock

ASYNC — creates Directives for later processing.
"""

from __future__ import annotations

import logging

from shopman.adapters import get_adapter
from shopman.ordering.models import Directive

logger = logging.getLogger(__name__)


def emit(order) -> None:
    """
    Schedule NFC-e emission for the order.

    Smart no-op if fiscal adapter is None (not configured).
    Creates a Directive with topic="fiscal.emit".

    ASYNC — retry-safe.
    """
    adapter = get_adapter("fiscal")
    if adapter is None:
        return

    # Idempotent: skip if already emitted
    if (order.data or {}).get("nfce_access_key"):
        return

    Directive.objects.create(
        topic="fiscal.emit",
        payload={
            "order_ref": order.ref,
            "items": _build_fiscal_items(order),
            "payment": (order.data or {}).get("payment", {}),
            "customer": (order.data or {}).get("customer", {}),
        },
    )

    logger.info("fiscal.emit: queued for order %s", order.ref)


def cancel(order) -> None:
    """
    Schedule NFC-e cancellation for the order.

    Smart no-op if fiscal adapter is None or NFC-e was never emitted.
    Creates a Directive with topic="fiscal.cancel".

    ASYNC — retry-safe.
    """
    adapter = get_adapter("fiscal")
    if adapter is None:
        return

    if not (order.data or {}).get("nfce_access_key"):
        return

    if (order.data or {}).get("nfce_cancelled"):
        return

    Directive.objects.create(
        topic="fiscal.cancel",
        payload={
            "order_ref": order.ref,
            "reason": (order.data or {}).get("cancellation_reason", "cancelled"),
        },
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
