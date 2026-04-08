"""
Stock orchestration service.

Core: StockService (holds), CatalogService (expand bundles)
Adapter: get_adapter("stock") → stock

The order lifecycle is:

  cart-add → services.availability.reserve(session_key)        [creates PENDING hold]
  checkout → CommitService creates Order with session_key
  on_commit → services.stock.hold(order)                       [adopts session holds]
  on_paid  → services.stock.fulfill(order)                     [PENDING→CONFIRMED→FULFILLED]
  cancel   → services.stock.release(order)                     [release adopted holds]

`hold(order)` ADOPTS the holds created at cart-add time (tagged with session_key
as reference). For order items without a matching session hold (e.g. POS,
marketplace, reorder), it creates fresh holds via the adapter as fallback.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from shopman.adapters import get_adapter
from shopman.offerman.service import CatalogService

logger = logging.getLogger(__name__)


def hold(order) -> None:
    """
    Reserve stock for all order items, expanding bundles.

    Strategy:
      1. Look up session holds tagged with order.session_key (created by
         services.availability.reserve at cart-add time).
      2. For each order item, adopt the matching session hold.
      3. For items without a session hold (POS, marketplace, reorder), create
         a fresh hold via the stock adapter.

    Saves the resulting hold_ids in order.data["hold_ids"]. SYNC.
    """
    items = order.snapshot.get("items", [])
    if not items:
        return

    session_key = getattr(order, "session_key", None)
    session_holds_by_sku = _load_session_holds(session_key) if session_key else {}

    adapter = get_adapter("stock")
    hold_ids: list[dict] = []

    for item in items:
        sku = item["sku"]
        qty = Decimal(str(item["qty"]))

        # Expand bundles into components
        components = _expand_if_bundle(sku, qty)

        for comp in components:
            comp_sku = comp["sku"]
            comp_qty = Decimal(str(comp["qty"]))

            # 1) Try to adopt an existing session hold for this SKU.
            adopted_id = _pop_matching_hold(session_holds_by_sku, comp_sku, comp_qty)
            if adopted_id:
                _retag_hold_for_order(adopted_id, order.ref)
                hold_ids.append(
                    {"sku": comp_sku, "hold_id": adopted_id, "qty": float(comp_qty)}
                )
                continue

            # 2) Fallback: create a fresh hold via the adapter.
            result = adapter.create_hold(
                sku=comp_sku,
                qty=comp_qty,
                reference=f"order:{order.ref}",
            )
            if not result.get("success"):
                logger.warning(
                    "stock.hold: create_hold failed sku=%s qty=%s code=%s",
                    comp_sku, comp_qty, result.get("error_code"),
                )
                continue

            hold_ids.append({
                "sku": comp_sku,
                "hold_id": result["hold_id"],
                "qty": float(comp_qty),
            })

    # Any session holds left over (e.g. items removed before checkout) — release.
    leftover_ids = [hid for ids in session_holds_by_sku.values() for hid in ids]
    if leftover_ids:
        adapter.release_holds(leftover_ids)

    order.data["hold_ids"] = hold_ids
    order.save(update_fields=["data", "updated_at"])

    logger.info("stock.hold: %d holds for order %s", len(hold_ids), order.ref)


def fulfill(order) -> None:
    """
    Fulfill (decrement) all holds for the order.

    Uses adapter.fulfill_hold() which transparently handles the
    PENDING → CONFIRMED → FULFILLED state machine.

    SYNC — must complete before notifying client.
    """
    hold_ids = (order.data or {}).get("hold_ids", [])
    if not hold_ids:
        return

    adapter = get_adapter("stock")
    errors = 0
    for entry in hold_ids:
        hold_id = entry.get("hold_id")
        if not hold_id:
            continue
        result = adapter.fulfill_hold(hold_id)
        if not result.get("success"):
            errors += 1
            logger.warning(
                "stock.fulfill: failed for %s: %s",
                hold_id, result.get("message"),
            )

    if errors:
        logger.error("stock.fulfill: %d errors for order %s", errors, order.ref)


def release(order) -> None:
    """
    Release all holds for the order (cancellation path).

    SYNC — immediate release.
    """
    hold_ids = (order.data or {}).get("hold_ids", [])
    if not hold_ids:
        return

    adapter = get_adapter("stock")
    ids = [entry.get("hold_id") for entry in hold_ids if entry.get("hold_id")]
    if ids:
        adapter.release_holds(ids)


def revert(order) -> None:
    """
    Revert stock for returned items (receive back into inventory).

    SYNC — devolução ao estoque.
    """
    adapter = get_adapter("stock")
    if not adapter:
        return

    for item in order.items.all():
        try:
            adapter.receive_return(
                sku=item.sku,
                qty=item.qty,
                reference=f"return:{order.ref}",
            )
        except Exception as exc:
            logger.warning(
                "stock.revert: failed for sku=%s order=%s: %s",
                item.sku, order.ref, exc,
            )


# ── helpers ──


def _expand_if_bundle(sku: str, qty: Decimal) -> list[dict]:
    """Expand bundle into components. Returns single-item list if not a bundle."""
    try:
        return CatalogService.expand(sku, qty)
    except Exception:
        return [{"sku": sku, "qty": qty}]


def _load_session_holds(session_key: str) -> dict[str, list[str]]:
    """Index active session holds by SKU.

    Returns {sku: [hold_id, ...]} for holds tagged with the given session_key
    that are still in PENDING/CONFIRMED state.
    """
    try:
        from shopman.stockman.models import Hold
        from shopman.stockman.models.enums import HoldStatus
    except ImportError:
        return {}

    holds = Hold.objects.filter(
        metadata__reference=session_key,
        status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
    )
    indexed: dict[str, list[str]] = {}
    for h in holds:
        indexed.setdefault(h.sku, []).append(h.hold_id)
    return indexed


def _pop_matching_hold(
    indexed: dict[str, list[str]],
    sku: str,
    qty: Decimal,
) -> str | None:
    """Pop and return one hold_id for `sku` from `indexed`, if present.

    Note: we don't try to match qty exactly. Cart UX may have created multiple
    holds for the same SKU as the customer adjusted quantities; we adopt them
    in FIFO order. Stockman tracks the actual reserved quantity per Hold row.
    """
    bucket = indexed.get(sku)
    if not bucket:
        return None
    return bucket.pop(0)


def _retag_hold_for_order(hold_id: str, order_ref: str) -> None:
    """Update Hold.metadata.reference from session_key to order ref.

    This is bookkeeping so the hold can be discovered later via
    `release_holds_for_reference("order:<ref>")` if needed.
    """
    try:
        from shopman.stockman.models import Hold
    except ImportError:
        return

    try:
        pk = int(hold_id.split(":")[1])
        hold = Hold.objects.get(pk=pk)
    except (ValueError, Hold.DoesNotExist):
        return

    metadata = dict(hold.metadata or {})
    metadata["reference"] = f"order:{order_ref}"
    hold.metadata = metadata
    hold.save(update_fields=["metadata"])
