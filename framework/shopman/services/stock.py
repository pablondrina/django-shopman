"""
Stock orchestration service.

Core: StockService (holds), CatalogService (expand bundles)
Adapter: get_adapter("stock") → stock_internal
"""

from __future__ import annotations

import logging
from decimal import Decimal

from shopman.adapters import get_adapter
from shopman.offering.service import CatalogService
from shopman.stocking.service import StockService

logger = logging.getLogger(__name__)


def hold(order) -> None:
    """
    Reserve stock for all order items, expanding bundles.

    Reads items from order.snapshot["items"]. For each item, expands bundles
    via CatalogService.expand(), then creates holds via StockService.hold().
    Saves hold_ids in order.data["hold_ids"].

    SYNC — must complete before responding to client.
    """
    items = order.snapshot.get("items", [])
    if not items:
        return

    hold_ids = []

    for item in items:
        sku = item["sku"]
        qty = Decimal(str(item["qty"]))

        # Expand bundles into components
        components = _expand_if_bundle(sku, qty)

        for comp in components:
            product = _get_product(comp["sku"])
            if not product:
                logger.warning("stock.hold: product not found for sku=%s", comp["sku"])
                continue

            hold_id = StockService.hold(
                quantity=comp["qty"],
                product=product,
            )
            hold_ids.append({"sku": comp["sku"], "hold_id": hold_id, "qty": float(comp["qty"])})

    order.data["hold_ids"] = hold_ids
    order.save(update_fields=["data", "updated_at"])

    logger.info("stock.hold: %d holds for order %s", len(hold_ids), order.ref)


def fulfill(order) -> None:
    """
    Fulfill (confirm) all holds for the order.

    Reads hold_ids from order.data["hold_ids"] and calls
    StockService.fulfill() for each.

    SYNC — must complete before confirming to client.
    """
    hold_ids = (order.data or {}).get("hold_ids", [])
    if not hold_ids:
        return

    errors = []
    for entry in hold_ids:
        hold_id = entry.get("hold_id")
        if not hold_id:
            continue
        try:
            StockService.fulfill(hold_id)
        except Exception as exc:
            errors.append(f"{hold_id}: {exc}")
            logger.warning("stock.fulfill: failed for %s: %s", hold_id, exc)

    if errors:
        logger.error("stock.fulfill: %d errors for order %s", len(errors), order.ref)


def release(order) -> None:
    """
    Release all holds for the order (cancellation path).

    Reads hold_ids from order.data["hold_ids"] and calls
    StockService.release() for each.

    SYNC — immediate release.
    """
    hold_ids = (order.data or {}).get("hold_ids", [])
    if not hold_ids:
        return

    for entry in hold_ids:
        hold_id = entry.get("hold_id")
        if not hold_id:
            continue
        try:
            StockService.release(hold_id)
        except Exception as exc:
            logger.warning("stock.release: failed for %s: %s", hold_id, exc)


def revert(order) -> None:
    """
    Revert stock for returned items (receive back into inventory).

    Creates positive stock moves via the stock adapter for each order item.

    SYNC — devolução ao estoque.
    """
    adapter = get_adapter("stock")
    if not adapter:
        return

    items = list(order.items.all())
    for item in items:
        try:
            adapter.receive_return(
                sku=item.sku,
                qty=item.qty,
                reference=f"return:{order.ref}",
            )
        except Exception as exc:
            logger.warning("stock.revert: failed for sku=%s order=%s: %s", item.sku, order.ref, exc)


# ── helpers ──


def _expand_if_bundle(sku: str, qty: Decimal) -> list[dict]:
    """Expand bundle into components. Returns single-item list if not a bundle."""
    try:
        return CatalogService.expand(sku, qty)
    except Exception:
        return [{"sku": sku, "qty": qty}]


def _get_product(sku: str):
    """Resolve SKU to Product via Offering."""
    from shopman.offering.models import Product

    return Product.objects.filter(sku=sku).first()
