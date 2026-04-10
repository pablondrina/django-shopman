"""Centralized alternatives service.

Single point of access for finding available alternative products across all contexts
(PDP, cart, stock-issue directives, API).
"""
from __future__ import annotations

import logging
from decimal import Decimal

from shopman.adapters import get_adapter
from shopman.utils.monetary import format_money

from ..web.constants import HAS_STOCKMAN, STOREFRONT_CHANNEL_REF

logger = logging.getLogger(__name__)


def find(sku: str, *, qty: Decimal = Decimal("1"), channel: str | None = None, limit: int = 4) -> list[dict]:
    """
    Busca alternativas disponíveis para o canal.
    Ponto único de consumo para todos os contextos.

    Returns:
        [{"sku", "name", "price_q", "price_display", "available_qty", "can_order"}, ...]
    """
    catalog = get_adapter("catalog")
    if not catalog:
        return []

    try:
        candidates = catalog.find_alternatives(sku, limit=limit * 2)
        if not candidates:
            return []
    except Exception as e:
        logger.warning("alternatives_candidates_failed sku=%s: %s", sku, e, exc_info=True)
        return []

    channel_ref = channel or STOREFRONT_CHANNEL_REF

    # Build availability map for all candidates in one batch query
    avail_map: dict[str, dict | None] = {}
    if HAS_STOCKMAN:
        try:
            from shopman.stockman.services.availability import (
                availability_for_skus,
                availability_scope_for_channel,
            )

            skus = [p.sku for p in candidates]
            scope = availability_scope_for_channel(channel_ref)
            avail_map = availability_for_skus(skus, **scope)
        except Exception as e:
            logger.warning("alternatives_availability_failed: %s", e, exc_info=True)

    # Build price map via listing
    price_map: dict[str, int] = {}
    try:
        from shopman.models import Channel

        channel_obj = Channel.objects.filter(ref=channel_ref).first()
        listing_ref = channel_obj.ref if channel_obj else None
        if listing_ref:
            skus = [p.sku for p in candidates]
            price_map = catalog.bulk_listing_price_map(skus, listing_ref)
    except Exception as e:
        logger.warning("alternatives_price_map_failed: %s", e, exc_info=True)

    result = []
    for product in candidates:
        if len(result) >= limit:
            break

        raw_avail = avail_map.get(product.sku)
        can_order, available_qty = _resolve_availability(raw_avail, product, qty)

        # Skip if not orderable and stockman is active
        if HAS_STOCKMAN and raw_avail is not None and not can_order:
            continue

        price_q = price_map.get(product.sku) or product.base_price_q
        price_display = f"R$ {format_money(price_q)}" if price_q else None

        result.append({
            "sku": product.sku,
            "name": product.name,
            "price_q": price_q,
            "price_display": price_display,
            "available_qty": available_qty,
            "can_order": can_order,
        })

    return result


def _resolve_availability(raw_avail: dict | None, product, qty: Decimal) -> tuple[bool, Decimal]:
    """Return (can_order, available_qty) from raw availability result."""
    if not product.is_available:
        return False, Decimal("0")
    if raw_avail is None:
        # No stockman data — assume available
        return True, Decimal("0")
    is_paused = raw_avail.get("is_paused", False) or not product.is_available
    total_orderable = raw_avail.get("total_orderable", Decimal("0"))
    can_order = total_orderable >= qty and not is_paused
    return can_order, total_orderable
