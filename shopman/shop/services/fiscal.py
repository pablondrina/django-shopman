"""
Fiscal (NFC-e) service.

ASYNC — creates Directives for later processing.
Smart no-op when fiscal_pool is empty (no backend configured).
"""

from __future__ import annotations

import logging

from shopman.shop import directives
from shopman.shop.directives import FISCAL_CANCEL_NFCE, FISCAL_EMIT_NFCE
from shopman.shop.fiscal import fiscal_pool

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

    payment = dict((order.data or {}).get("payment", {}) or {})
    payment.setdefault("amount_q", order.total_q)

    directives.queue(
        FISCAL_EMIT_NFCE, order,
        items=_build_fiscal_items(order),
        payment=payment,
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
    products_by_sku = _products_by_sku([item.sku for item in order.items.all()])
    for item in order.items.all():
        product = products_by_sku.get(item.sku)
        metadata = dict(getattr(product, "metadata", None) or {})
        fiscal = dict((item.meta or {}).get("fiscal") or metadata.get("fiscal") or {})
        items.append({
            "sku": item.sku,
            "name": item.name,
            "qty": str(item.qty.normalize()) if hasattr(item.qty, "normalize") else float(item.qty),
            "unit": getattr(product, "unit", "") or fiscal.get("unit") or "UN",
            "unit_price_q": item.unit_price_q,
            "total_q": item.line_total_q,
            "fiscal": fiscal,
        })
    return items


def _products_by_sku(skus: list[str]) -> dict[str, object]:
    if not skus:
        return {}
    try:
        from shopman.offerman.models import Product

        return {
            product.sku: product
            for product in Product.objects.filter(sku__in=set(skus)).only("sku", "unit", "metadata")
        }
    except Exception:
        logger.debug("fiscal.emit: product metadata lookup failed", exc_info=True)
        return {}
