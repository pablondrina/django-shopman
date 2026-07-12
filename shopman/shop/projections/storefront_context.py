"""Storefront context — read-side facades for storefront-facing read paths.

Small, pure queries that collect contextual state (v1 views and presentation
builders consume them through this stable import path):

- ``popular_skus`` — most-favourited SKUs across customer insights.
- ``happy_hour_state`` — current happy-hour window + discount percent.
- ``session_pricing_hints`` — fulfillment type + subtotal from the active
  cart session, matching what DiscountModifier sees at checkout.

A clean read facade (policy/data, no presentation), so it lives in the
orchestrator read-side (``shop/projections/``).

The minimum-order progress and upsell read-models drained to
``shop/projections/cart.py`` (data) + ``storefront/presentation`` (display).
"""

from __future__ import annotations

import logging
from datetime import time

from django.utils import timezone
from shopman.guestman.contrib.insights import InsightService

logger = logging.getLogger(__name__)

DEFAULT_STOREFRONT_CHANNEL_REF = "web"


_HAPPY_HOUR_INACTIVE: dict = {
    "active": False,
    "discount_percent": 0,
    "start": "",
    "end": "",
}


def popular_skus(limit: int = 5) -> set[str]:
    """Aggregate favourite SKUs across customer insights.

    Returns a set of SKUs ordered by frequency×qty. Falls back to an empty
    set if guestman insights are unavailable or return nothing.
    """
    try:
        insights = InsightService.favorite_product_samples(limit=200)
        sku_counts: dict[str, int] = {}
        for favorites in insights:
            if not favorites:
                continue
            for fav in favorites:
                sku = fav.get("sku", "") if isinstance(fav, dict) else str(fav)
                if not sku:
                    continue
                qty = fav.get("qty", 1) if isinstance(fav, dict) else 1
                sku_counts[sku] = sku_counts.get(sku, 0) + qty
        if not sku_counts:
            return set()
        sorted_skus = sorted(sku_counts, key=sku_counts.get, reverse=True)
        return set(sorted_skus[:limit])
    except Exception as e:
        logger.warning("popular_skus_failed: %s", e, exc_info=True)
        return set()


def happy_hour_state() -> dict:
    """Return the current happy-hour state.

    Gated on the enabled ``happy_hour`` RuleConfig — the **same source** the
    ``TimeWindowDiscountModifier`` reads for window/percent — so the badge and
    the applied discount can never diverge. Returns inactive when the rule is
    absent or disabled.
    """
    try:
        from shopman.shop.rules.engine import get_rule_params

        params = get_rule_params("happy_hour")
        if not params:
            return _HAPPY_HOUR_INACTIVE

        raw_start = params.get("start", "17:30")
        raw_end = params.get("end", "18:00")
        discount_percent = params.get("discount_percent", 25)

        sh, sm = map(int, raw_start.split(":"))
        eh, em = map(int, raw_end.split(":"))
        start = time(sh, sm)
        end = time(eh, em)
        now = timezone.localtime().time()
        active = start <= now < end
        return {
            "active": active,
            "discount_percent": discount_percent,
            "start": raw_start,
            "end": raw_end,
        }
    except Exception as e:
        logger.warning("happy_hour_check_failed: %s", e, exc_info=True)
        return _HAPPY_HOUR_INACTIVE


def session_pricing_hints(request) -> tuple[str, int]:
    """Return ``(fulfillment_type, subtotal_q)`` from the active cart session.

    Feeds ``CatalogService.get_price``'s context so the menu shows the same
    discounts the checkout will apply. Returns ``("", 0)`` when there is no
    active session or when anything in the lookup fails.
    """
    if request is None:
        return "", 0
    try:
        from shopman.orderman.models import Session

        from shopman.shop.models import Channel

        key = request.session.get("cart_session_key")
        if not key:
            return "", 0
        ch = Channel.objects.filter(ref=DEFAULT_STOREFRONT_CHANNEL_REF).first()
        if not ch:
            return "", 0
        sess = Session.objects.filter(
            session_key=key,
            channel_ref=ch.ref,
            state="open",
        ).first()
        if not sess:
            return "", 0
        ft = (sess.data or {}).get("fulfillment_type") or ""
        total = sum(int(line.get("line_total_q", 0) or 0) for line in (sess.items or []))
        return ft, total
    except Exception as e:
        logger.warning("session_pricing_hints_failed: %s", e, exc_info=True)
        return "", 0
