"""Backstage projection helpers — POS-specific utilities."""

from __future__ import annotations

import logging
from datetime import date

from django.conf import settings

from shopman.backstage.constants import POS_CHANNEL_REF

logger = logging.getLogger(__name__)

HAS_STOCKMAN = True


def _get_availability(sku: str, *, target_date: date | None = None) -> dict | None:
    """Breakdown de estoque para o canal POS."""
    if not HAS_STOCKMAN:
        return None
    try:
        from shopman.stockman.services.availability import availability_for_sku

        from shopman.shop.adapters import stock as stock_adapter

        scope = stock_adapter.get_channel_scope(POS_CHANNEL_REF)
        return availability_for_sku(
            sku,
            target_date=target_date,
            safety_margin=scope["safety_margin"],
            allowed_positions=scope["allowed_positions"],
            excluded_positions=scope.get("excluded_positions"),
        )
    except Exception as e:
        logger.warning("availability_lookup_failed sku=%s: %s", sku, e, exc_info=True)
        return None


def _line_item_is_d1(product, *, listing_ref: str | None = None) -> bool:
    """True if SKU has only D-1 stock in its availability scope. POS internal use only."""
    avail = _get_availability(product.sku)
    if not avail:
        return False
    from decimal import Decimal

    breakdown = avail.get("breakdown", {})
    ready = breakdown.get("ready", Decimal("0"))
    in_prod = breakdown.get("in_production", Decimal("0"))
    d1 = breakdown.get("d1", Decimal("0"))
    return d1 > 0 and ready == 0 and in_prod == 0
