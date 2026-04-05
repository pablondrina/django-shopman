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
    """Resolve SKU to Product via Offering."""
    from shopman.offering.models import Product

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
    from shopman.stocking.service import Stock as stock

    try:
        product = _get_product(sku)
    except ObjectDoesNotExist:
        return {
            "available": False,
            "available_qty": Decimal("0"),
            "message": f"Produto não encontrado: {sku}",
        }

    if allowed_positions is not None:
        from shopman.stocking.models import Position

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
    **metadata,
) -> dict:
    """
    Create a stock hold for a SKU.

    Returns:
        {"success": bool, "hold_id": str | None, "error_code": str | None,
         "message": str | None, "expires_at": datetime | None, "is_planned": bool}
    """
    from shopman.stocking.exceptions import StockError
    from shopman.stocking.service import Stock as stock

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

    try:
        hold_id = stock.hold(
            qty,
            product,
            target_date=target_date or date.today(),
            expires_at=expires_at,
            **hold_kwargs,
        )

        from shopman.stocking.models import Hold

        pk = int(hold_id.split(":")[1])
        hold = Hold.objects.get(pk=pk)

        is_planned = False
        if hold.quant and hold.quant.target_date is not None:
            is_planned = True
            hold.expires_at = timezone.now() + timedelta(hours=planned_hold_ttl_hours)
            hold.save(update_fields=["expires_at"])

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


def fulfill_hold(hold_id: str) -> dict:
    """
    Fulfill a confirmed hold (decrements stock).

    Handles PENDING → CONFIRMED → FULFILLED transition automatically.

    Returns:
        {"success": bool, "error_code": str | None, "message": str | None}
    """
    from shopman.stocking.exceptions import StockError
    from shopman.stocking.models import Hold
    from shopman.stocking.models.enums import HoldStatus
    from shopman.stocking.service import Stock as stock

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

        stock.fulfill(hold_id)
        return {"success": True, "error_code": None, "message": None}
    except StockError as e:
        return {
            "success": False,
            "error_code": e.code if hasattr(e, "code") else "fulfill_failed",
            "message": str(e),
        }


def release_holds(hold_ids: list[str]) -> None:
    """Release multiple holds (cancel reservations)."""
    from shopman.stocking.exceptions import StockError
    from shopman.stocking.service import Stock as stock

    for hold_id in hold_ids:
        try:
            stock.release(hold_id, reason="Liberado via Shopman")
        except StockError:
            logger.debug("release_holds: Hold %s already released or invalid", hold_id)


def get_alternatives(sku: str, qty: Decimal, *, limit: int = 5) -> list[dict]:
    """
    Find alternative products with sufficient stock.

    Returns:
        [{"sku": str, "name": str, "available_qty": Decimal}, ...]
    """
    try:
        from shopman.offering.contrib.suggestions import find_alternatives
    except ImportError:
        return []

    try:
        candidates = find_alternatives(sku, limit=limit)
    except Exception:
        return []

    from shopman.stocking.service import Stock as stock

    alternatives = []
    for product in candidates:
        try:
            avail_qty = stock.available(product.sku)
            if avail_qty >= qty:
                alternatives.append({
                    "sku": product.sku,
                    "name": product.name,
                    "available_qty": Decimal(str(avail_qty)),
                })
        except Exception:
            pass
    return alternatives


def release_holds_for_reference(reference: str) -> int:
    """Release all active holds for a given reference (e.g. order ref)."""
    from shopman.stocking.exceptions import StockError
    from shopman.stocking.models import Hold
    from shopman.stocking.models.enums import HoldStatus
    from shopman.stocking.service import Stock as stock

    try:
        holds = Hold.objects.filter(
            status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
            metadata__reference=reference,
        )
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
    from shopman.stocking.services.movements import StockMovements

    full_reason = f"{reason} (ref: {reference})" if reference else reason
    StockMovements.receive(quantity=qty, sku=sku, reason=full_reason)
