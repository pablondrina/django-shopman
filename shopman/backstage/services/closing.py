"""Day closing command service.

The DayClosing audit record is owned by Backstage, while physical stock
movements are delegated to Stockman. Views call this service so HTTP code does
not manipulate inventory directly.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from django.db import transaction
from shopman.stockman import Position, Quant
from shopman.stockman.services.movements import StockMovements

from shopman.backstage.models import DayClosing


def perform_day_closing(
    *,
    user,
    items: Iterable,
    quantities_by_sku: dict[str, str],
    closing_date: date | None = None,
) -> date:
    """Execute day closing and return the closing date."""
    closing_date = closing_date or date.today()
    if DayClosing.objects.filter(date=closing_date).exists():
        raise ValueError("Fechamento de hoje já foi realizado.")

    snapshot = []
    with transaction.atomic():
        for item in items:
            sku = item.sku
            qty_reported = _parse_qty(quantities_by_sku.get(sku, "0"))

            if qty_reported <= 0:
                snapshot.append(_snapshot(item, qty_reported=qty_reported, qty_d1=0, qty_loss=0))
                continue

            qty_unsold = min(qty_reported, item.qty_available)
            qty_d1 = 0
            qty_loss = 0

            if item.classification == "d1":
                ontem_pos = Position.objects.filter(ref="ontem").first()
                if ontem_pos:
                    _issue_from_saleable(sku, qty_unsold, f"fechamento:{closing_date}")
                    StockMovements.receive(
                        quantity=Decimal(qty_unsold),
                        sku=sku,
                        position=ontem_pos,
                        batch="D-1",
                        reason=f"d1:{closing_date}",
                        user=user,
                    )
                    qty_d1 = qty_unsold
            elif item.classification == "loss":
                _issue_from_saleable(sku, qty_unsold, f"perda:{closing_date}")
                qty_loss = qty_unsold

            snapshot.append(
                _snapshot(
                    item,
                    qty_reported=qty_reported,
                    qty_unsold=qty_unsold,
                    qty_d1=qty_d1,
                    qty_loss=qty_loss,
                )
            )

        DayClosing.objects.create(
            date=closing_date,
            closed_by=user,
            data=snapshot,
        )

    return closing_date


def _parse_qty(raw_qty) -> int:
    try:
        return max(0, int(str(raw_qty).strip()))
    except (ValueError, TypeError):
        return 0


def _snapshot(item, *, qty_reported: int, qty_unsold: int = 0, qty_d1: int, qty_loss: int) -> dict:
    return {
        "sku": item.sku,
        "qty_reported": qty_reported,
        "qty_applied": qty_unsold,
        "qty_discrepancy": qty_reported - qty_unsold,
        "qty_remaining": item.qty_available - qty_unsold,
        "qty_d1": qty_d1,
        "qty_loss": qty_loss,
    }


def _issue_from_saleable(sku, quantity, reason) -> None:
    """Issue stock from saleable positions, excluding D-1 stock."""
    quants = (
        Quant.objects.filter(
            sku=sku,
            position__is_saleable=True,
            _quantity__gt=0,
        )
        .exclude(position__ref="ontem")
        .select_for_update()
        .order_by("pk")
    )
    remaining = Decimal(quantity)
    for quant in quants:
        if remaining <= 0:
            break
        take = min(remaining, quant._quantity)
        StockMovements.issue(quantity=take, quant=quant, reason=reason)
        remaining -= take
