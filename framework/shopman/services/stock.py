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

`hold(order)` ADOPTS session holds **by quantity, not by SKU-first**: multiple
session holds for the same SKU are summed up to meet the ordered qty, and a
fresh hold is created via the adapter for any unmet remainder. This is the
fix for the sangria where a stepper that created two holds of qty=2 each
ended up adopting only one of them.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from shopman.adapters import get_adapter
from shopman.services.order_helpers import get_commitment_date

logger = logging.getLogger(__name__)


def hold(order) -> None:
    """
    Reserve stock for all order items, expanding bundles.

    Strategy:
      1. Look up session holds tagged with order.session_key (created by
         services.availability.reserve at cart-add time), indexed per SKU as
         a FIFO list of `(hold_id, qty)` pairs.
      2. For each order component, consume holds from the bucket until the
         component's required qty is met (possibly adopting multiple holds).
      3. Create a fresh hold via the adapter for any unmet remainder (POS,
         marketplace, reorder, or partial session coverage).
      4. Release any session holds not consumed (e.g. items removed before
         checkout that weren't reconciled on the cart side).

    Saves the resulting hold_ids in order.data["hold_ids"]. SYNC.
    """
    items = order.snapshot.get("items", [])
    if not items:
        return

    target_date = get_commitment_date(order)
    adopt_session_holds = target_date in (None, date.today())
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

            # 1) Adopt session holds by quantity until comp_qty is met.
            if adopt_session_holds:
                adopted_pairs, unmet_qty = _adopt_holds_for_qty(
                    session_holds_by_sku, comp_sku, comp_qty,
                )
            else:
                adopted_pairs, unmet_qty = [], comp_qty
            for hid, hqty in adopted_pairs:
                _retag_hold_for_order(hid, order.ref)
                hold_ids.append(
                    {"sku": comp_sku, "hold_id": hid, "qty": float(hqty)}
                )

            if unmet_qty <= 0:
                continue

            # 2) Fallback: create a fresh hold via the adapter for the remainder.
            result = adapter.create_hold(
                sku=comp_sku,
                qty=unmet_qty,
                reference=f"order:{order.ref}",
                target_date=target_date,
            )
            if not result.get("success"):
                logger.warning(
                    "stock.hold: create_hold failed sku=%s qty=%s code=%s",
                    comp_sku, unmet_qty, result.get("error_code"),
                )
                continue

            hold_ids.append({
                "sku": comp_sku,
                "hold_id": result["hold_id"],
                "qty": float(unmet_qty),
            })

    # Any session holds left over (e.g. items removed before checkout without
    # calling availability.reconcile) — release.
    leftover_ids = [
        hid for pairs in session_holds_by_sku.values() for hid, _ in pairs
    ]
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
        catalog = get_adapter("catalog")
        return catalog.expand_bundle(sku, qty)
    except Exception:
        logger.exception("stock._expand_if_bundle: unexpected error expanding sku=%s", sku)
        return [{"sku": sku, "qty": qty}]


def _load_session_holds(session_key: str) -> dict[str, list[tuple[str, Decimal]]]:
    """Index active session holds by SKU, preserving (hold_id, qty) pairs.

    Returns {sku: [(hold_id, qty), ...]} for holds tagged with the given
    session_key that are still in PENDING/CONFIRMED state. Order within a
    bucket is FIFO (by Hold.pk).
    """
    adapter = get_adapter("stock")
    holds = adapter.find_holds_by_reference(session_key)
    indexed: dict[str, list[tuple[str, Decimal]]] = {}
    for hold_id, sku, qty in holds:
        indexed.setdefault(sku, []).append((hold_id, qty))
    return indexed


def _adopt_holds_for_qty(
    indexed: dict[str, list[tuple[str, Decimal]]],
    sku: str,
    required_qty: Decimal,
) -> tuple[list[tuple[str, Decimal]], Decimal]:
    """Consume session holds for `sku` until `required_qty` is met.

    Returns `(adopted_pairs, unmet_qty)` where `adopted_pairs` is a list of
    `(hold_id, hold_qty)` popped from the bucket in FIFO order, and
    `unmet_qty` is the remaining quantity to cover via a fresh hold (zero
    when the session holds fully satisfy the requirement).

    Over-adoption (last hold's qty pushes the total past required_qty) is
    accepted: the excess stays reserved to the order, commit consolidates
    everything in `order.data["hold_ids"]`, and `fulfill_hold` drains each
    hold fully at pay-time. Splitting the tail hold would require a new
    Stockman API and the minor drift is absorbed.
    """
    bucket = indexed.get(sku, [])
    adopted: list[tuple[str, Decimal]] = []
    remaining = required_qty
    while bucket and remaining > 0:
        hid, hqty = bucket.pop(0)
        adopted.append((hid, hqty))
        remaining -= hqty
    unmet = remaining if remaining > 0 else Decimal("0")
    return adopted, unmet


def _retag_hold_for_order(hold_id: str, order_ref: str) -> None:
    """Update Hold.metadata.reference from session_key to order ref.

    This is bookkeeping so the hold can be discovered later via
    `release_holds_for_reference("order:<ref>")` if needed.
    """
    adapter = get_adapter("stock")
    adapter.retag_hold_reference(hold_id, f"order:{order_ref}")
