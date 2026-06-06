from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest
from shopman.utils.monetary import format_money

from shopman.shop.projections import catalog_context
from shopman.shop.projections.storefront_context import session_pricing_hints

from ..constants import STOREFRONT_CHANNEL_REF

logger = logging.getLogger(__name__)


def _to_storefront_avail(raw_avail: dict | None, product: Any) -> dict | None:
    """Convert raw availability_for_sku result to simplified storefront view.

    The storefront never consumes internal breakdown ({ready, in_production, d1}).
    Returns:
        {available_qty, can_order, is_paused, had_stock, state}
    or None if raw_avail is None.
    """
    return catalog_context.storefront_availability(raw_avail, is_sellable=product.is_sellable)


def _storefront_availability_state(*, can_order: bool, had_stock: bool, is_paused: bool) -> str:
    """Map internal availability facts to the only UI states the storefront needs."""
    if can_order:
        return "available"
    if had_stock and not is_paused:
        return "sold_out"
    return "unavailable"


def _availability_badge(avail: dict | None, product: Any) -> dict:
    """
    Determine the availability badge for a product.

    ``avail`` must be the simplified storefront format from ``_to_storefront_avail()``,
    NOT the raw breakdown from availability_for_sku(). Returns:
      {label, css_class, can_add_to_cart}

    Customer-facing states (AVAILABILITY-PLAN vocabulary):
    - available: can_order=True → no badge (implicit)
    - qualquer caso de can_order=False (paused, sold-out, etc.) → "Indisponível"
    """
    if not product.is_sellable:
        return {"label": "Indisponível", "css_class": "badge-unavailable", "can_add_to_cart": False}

    if avail is None:
        # No stockman module — fall back to product.is_sellable flag
        return {"label": "", "css_class": "", "can_add_to_cart": product.is_sellable}

    state = avail.get("state") or _storefront_availability_state(
        can_order=avail.get("can_order", True),
        had_stock=avail.get("had_stock", False),
        is_paused=avail.get("is_paused", False),
    )
    if state == "available":
        return {"label": "", "css_class": "badge-available", "can_add_to_cart": True}
    return {"label": "Indisponível", "css_class": "badge-unavailable", "can_add_to_cart": False}


def annotate_products(
    products: list[Any],
    listing_ref: str | None = None,
    popular_skus: set[str] | None = None,
    *,
    session_total_q: int | None = None,
    fulfillment_type: str | None = None,
    request: HttpRequest | None = None,
) -> list[dict]:
    """Build template-ready list with canonical price quote and availability."""
    if request is not None and (session_total_q is None or fulfillment_type is None):
        ft_hint, sub_hint = session_pricing_hints(request)
        if fulfillment_type is None:
            fulfillment_type = ft_hint
        if session_total_q is None:
            session_total_q = sub_hint
    if session_total_q is None:
        session_total_q = 0
    if fulfillment_type is None:
        fulfillment_type = ""

    skus = [p.sku for p in products]

    # ── Batch: collections per SKU ────────────────────────────────────────────
    sku_collections = catalog_context.collection_refs_by_sku(skus)

    # ── Batch: prices — one query for all SKUs ────────────────────────────────
    price_map: dict[str, int] = {}
    if listing_ref:
        price_map = catalog_context.listing_price_map(skus, listing_ref)

    # ── Batch: availability — one call for all SKUs ───────────────────────────
    avail_map = catalog_context.availability_for_skus(skus, channel_ref=STOREFRONT_CHANNEL_REF)

    result = []
    for p in products:
        base_q = price_map.get(p.sku) if listing_ref else None
        if base_q is None:
            base_q = p.base_price_q

        avail_raw = avail_map.get(p.sku)
        avail = _to_storefront_avail(avail_raw, p)
        badge = _availability_badge(avail, p)
        cols = sku_collections.get(p.sku, [])

        price = catalog_context.contextual_price(
            p.sku,
            qty=1,
            listing_ref=listing_ref,
            context={
                "sku_collections": cols,
                "session_total_q": session_total_q,
                "fulfillment_type": fulfillment_type,
            },
            list_unit_price_q=base_q,
        )

        promo_badge = None
        promo_price_display = None
        promo_original_price_display = None
        has_promo_price = False

        if price.adjustments:
            has_promo_price = price.final_unit_price_q < price.list_unit_price_q
            adjustment = price.adjustments[0]
            if has_promo_price:
                promo_price_display = f"R$ {format_money(price.final_unit_price_q)}"
                promo_original_price_display = f"R$ {format_money(price.list_unit_price_q)}"
                promo_badge = {
                    "name": adjustment.metadata.get("promotion_name", adjustment.label),
                    "type": adjustment.metadata.get("promotion_type"),
                    "value": adjustment.metadata.get("promotion_value"),
                    "label": adjustment.metadata.get("badge_label", adjustment.label),
                }

        effective_q = price.final_unit_price_q
        price_display = f"R$ {format_money(effective_q)}" if effective_q else None

        # available_qty for stepper clamp (WP-AV-07). None when Stockman
        # hasn't reported a number (untracked SKU or demand_ok policy).
        available_qty = None
        if avail_raw is not None:
            total = avail_raw.get("total_promisable")
            if total is not None:
                try:
                    from decimal import Decimal as _D
                    available_qty = int(_D(str(total)))
                except Exception:
                    logger.debug("product_cards.annotate_products degraded; using fallback", exc_info=True)
                    available_qty = None

        result.append({
            "product": p,
            "price_q": effective_q,
            "price_display": price_display,
            "badge": badge,
            "availability": avail,
            "available_qty": available_qty,
            "promo_badge": promo_badge,
            "has_promo_price": has_promo_price,
            "promo_price_display": promo_price_display,
            "promo_original_price_display": promo_original_price_display,
            "is_popular": popular_skus is not None and p.sku in popular_skus,
        })
    return result
