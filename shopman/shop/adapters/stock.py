"""
Internal stock adapter — delegates to Stockman (Core).

Core: StockService (holds, movements, queries)
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

logger = logging.getLogger(__name__)


def _get_product(sku: str):
    """Resolve SKU to Product via Offerman."""
    from shopman.offerman.models import Product

    return Product.objects.get(sku=sku)


def check_availability(
    sku: str,
    qty: Decimal,
    target_date: date | None = None,
    *,
    safety_margin: int = 0,
    allowed_positions: list[str] | None = None,
) -> dict:
    """
    Check stock availability for a SKU.

    Returns:
        {"available": bool, "available_qty": Decimal, "message": str | None}
    """
    from shopman.stockman.service import Stock as stock

    try:
        product = _get_product(sku)
    except ObjectDoesNotExist:
        return {
            "available": False,
            "available_qty": Decimal("0"),
            "message": f"Produto não encontrado: {sku}",
        }

    if allowed_positions is not None:
        from shopman.stockman.models import Position

        total = Decimal("0")
        positions = Position.objects.filter(ref__in=allowed_positions)
        for pos in positions:
            total += stock.available(product, target_date=target_date, position=pos)
        available = total
    else:
        available = stock.available(product, target_date=target_date)

    if target_date and target_date > date.today() and safety_margin > 0:
        available = max(Decimal("0"), available - Decimal(str(safety_margin)))

    return {
        "available": qty <= available,
        "available_qty": Decimal(str(available)),
        "message": None if qty <= available else f"Disponível: {available}",
    }


def create_hold(
    sku: str,
    qty: Decimal,
    ttl_minutes: int = 30,
    *,
    target_date: date | None = None,
    reference: str | None = None,
    planned_hold_ttl_hours: int = 48,
    channel_ref: str | None = None,
    **metadata,
) -> dict:
    """
    Create a stock hold for a SKU.

    When ``channel_ref`` is provided, the channel's stock scope
    (``allowed_positions`` / ``excluded_positions`` from ``ChannelConfig.stock``)
    is resolved and passed through to the Stockman hold so eligibility matches
    the availability read.

    Returns:
        {"success": bool, "hold_id": str | None, "error_code": str | None,
         "message": str | None, "expires_at": datetime | None, "is_planned": bool}
    """
    from shopman.stockman.exceptions import StockError
    from shopman.stockman.service import Stock as stock

    try:
        product = _get_product(sku)
    except ObjectDoesNotExist:
        return {
            "success": False,
            "hold_id": None,
            "error_code": "product_not_found",
            "message": f"Produto não encontrado: {sku}",
            "expires_at": None,
            "is_planned": False,
        }

    expires_at = timezone.now() + timedelta(minutes=ttl_minutes)

    hold_kwargs = dict(metadata)
    if reference:
        hold_kwargs["reference"] = reference

    scope = get_channel_scope(channel_ref) if channel_ref else {}
    allowed_positions = scope.get("allowed_positions")
    excluded_positions = scope.get("excluded_positions")

    try:
        hold_id = stock.hold(
            qty,
            product,
            target_date=target_date or date.today(),
            expires_at=expires_at,
            allowed_positions=allowed_positions,
            excluded_positions=excluded_positions,
            **hold_kwargs,
        )

        from shopman.stockman.models import Hold

        pk = int(hold_id.split(":")[1])
        hold = Hold.objects.get(pk=pk)

        # Planned holds (AVAILABILITY-PLAN §8): holds on planned quants and
        # demand-only holds (quant=None) are INDEFINITE. The TTL starts
        # running only at materialization (``planning.realize()`` fills in
        # ``expires_at`` when the planned stock is produced). The old 48h
        # TTL on planned holds meant customers could silently lose their
        # reservation before production caught up — unacceptable.
        #
        # ``metadata.planned`` is the durable marker used by the cart
        # projection to classify the line as "Aguardando confirmação" or
        # "Tudo pronto! Confirme": once materialize() runs, the hold keeps
        # the flag AND gets a TTL, which is how the UI distinguishes a
        # post-materialization hold from a vanilla 30-min cart hold.
        is_planned = False
        is_indefinite = hold.quant is None or (
            hold.quant is not None and hold.quant.target_date is not None
        )
        if is_indefinite:
            is_planned = hold.quant is not None and hold.quant.target_date is not None
            hold.expires_at = None
            hold.metadata = {**(hold.metadata or {}), "planned": True}
            hold.save(update_fields=["expires_at", "metadata"])

        return {
            "success": True,
            "hold_id": hold_id,
            "error_code": None,
            "message": None,
            "expires_at": hold.expires_at,
            "is_planned": is_planned,
        }
    except StockError as e:
        return {
            "success": False,
            "hold_id": None,
            "error_code": e.code if hasattr(e, "code") else "hold_failed",
            "message": str(e),
            "expires_at": None,
            "is_planned": False,
        }
    except Exception as e:
        logger.warning("create_hold failed for SKU %s: %s", sku, e, exc_info=True)
        return {
            "success": False,
            "hold_id": None,
            "error_code": "hold_failed",
            "message": str(e),
            "expires_at": None,
            "is_planned": False,
        }


def fulfill_hold(hold_id: str, *, qty: Decimal | None = None) -> dict:
    """
    Fulfill a confirmed hold (decrements stock).

    Handles PENDING → CONFIRMED → FULFILLED transition automatically.

    `qty` overrides the hold's reserved quantity for the Move delta, allowing
    partially-adopted holds (where the session hold exceeded the ordered qty)
    to consume only the needed amount.

    Returns:
        {"success": bool, "error_code": str | None, "message": str | None}
    """
    from shopman.stockman import Hold, HoldStatus, StockError
    from shopman.stockman.service import Stock as stock

    pk = int(hold_id.split(":")[1])
    try:
        hold = Hold.objects.get(pk=pk)
    except Hold.DoesNotExist:
        return {
            "success": False,
            "error_code": "hold_not_found",
            "message": f"Hold {hold_id} não encontrado",
        }

    if hold.status == HoldStatus.FULFILLED:
        return {"success": True, "error_code": None, "message": None}

    try:
        if hold.status == HoldStatus.PENDING:
            try:
                stock.confirm(hold_id)
            except StockError:
                hold.refresh_from_db()
                if hold.status not in (HoldStatus.CONFIRMED, HoldStatus.FULFILLED):
                    raise

        stock.fulfill(hold_id, quantity=qty)
        return {"success": True, "error_code": None, "message": None}
    except StockError as e:
        return {
            "success": False,
            "error_code": e.code if hasattr(e, "code") else "fulfill_failed",
            "message": str(e),
        }


def release_holds(hold_ids: list[str]) -> None:
    """Release multiple holds (cancel reservations)."""
    from shopman.stockman import StockError
    from shopman.stockman.service import Stock as stock

    for hold_id in hold_ids:
        try:
            stock.release(hold_id, reason="Liberado via Shopman")
        except StockError:
            logger.debug("release_holds: Hold %s already released or invalid", hold_id)


def release_holds_for_reference(reference: str) -> int:
    """Release all active holds for a given reference (e.g. order ref)."""
    from shopman.stockman import StockError, StockHolds
    from shopman.stockman.service import Stock as stock

    try:
        holds = StockHolds.find_active_by_reference(reference)
        count = 0
        for hold in holds:
            try:
                stock.release(hold.hold_id, reason="Idempotency cleanup")
                count += 1
            except StockError:
                pass
        return count
    except Exception:
        return 0


def receive_return(
    sku: str,
    qty: Decimal,
    *,
    reference: str | None = None,
    reason: str = "Devolução",
) -> None:
    """Receive returned stock back into inventory."""
    from shopman.stockman.services.movements import StockMovements

    full_reason = f"{reason} (ref: {reference})" if reference else reason
    StockMovements.receive(quantity=qty, sku=sku, reason=full_reason)


# ── Session hold queries ─────────────────────────────────────────────


def find_holds_by_reference(
    reference: str,
    *,
    sku: str | None = None,
) -> list[tuple[str, str, Decimal]]:
    """Find active holds (PENDING/CONFIRMED) tagged with `reference`.

    Returns:
        List of (hold_id, sku, qty) tuples ordered by pk (FIFO).
    """
    from shopman.stockman import HoldStatus, StockHolds

    holds = StockHolds.find_by_reference(
        reference,
        sku=sku,
        status_in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
    )
    return [(h.hold_id, h.sku, Decimal(str(h.quantity))) for h in holds]


def retag_hold_reference(hold_id: str, new_reference: str) -> bool:
    """Update hold's reference tag (e.g. session_key → order ref).

    Returns True if updated, False if hold not found.
    """
    from shopman.stockman import StockHolds

    return StockHolds.retag_reference(hold_id, new_reference)


# ── Availability queries ─────────────────────────────────────────────


def get_availability(
    sku: str,
    *,
    target_date: date | None = None,
    safety_margin: int = 0,
    allowed_positions: list[str] | None = None,
    excluded_positions: list[str] | None = None,
) -> dict:
    """Return availability info for a SKU.

    Delegates to Stockman's availability_for_sku(). Returns a dict with
    keys: sku, total_available, total_promisable, total_reserved,
    breakdown, is_planned, is_paused, is_tracked, positions.
    """
    from shopman.stockman.services.availability import availability_for_sku

    return availability_for_sku(
        sku,
        target_date=target_date,
        safety_margin=safety_margin,
        allowed_positions=allowed_positions,
        excluded_positions=excluded_positions,
    )


def get_channel_scope(channel_ref: str | None) -> dict:
    """Return stock scope for a channel.

    Keys: ``safety_margin`` (int), ``allowed_positions`` (list[str] | None),
    ``excluded_positions`` (list[str] | None).

    The scope is resolved from ``ChannelConfig.stock`` (cascade: defaults →
    Shop.defaults → Channel.config). When no ``channel_ref`` is given the
    Stockman stub is returned so non-channel-scoped callers keep working.
    """
    if not channel_ref:
        from shopman.stockman.services.availability import (
            availability_scope_for_channel,
        )

        base = availability_scope_for_channel(channel_ref)
        base.setdefault("excluded_positions", None)
        return base

    from shopman.shop.config import ChannelConfig

    cfg = ChannelConfig.for_channel(channel_ref)
    return {
        "safety_margin": cfg.stock.safety_margin,
        "allowed_positions": cfg.stock.allowed_positions,
        "excluded_positions": cfg.stock.excluded_positions,
    }


def get_promise_decision(
    sku: str,
    qty,
    *,
    target_date: date | None = None,
    safety_margin: int = 0,
    allowed_positions: list[str] | None = None,
    excluded_positions: list[str] | None = None,
):
    """Return Stockman's explicit operational promise decision for a SKU."""
    from shopman.stockman.services.availability import promise_decision_for_sku

    return promise_decision_for_sku(
        sku,
        qty,
        target_date=target_date,
        safety_margin=safety_margin,
        allowed_positions=allowed_positions,
        excluded_positions=excluded_positions,
    )
