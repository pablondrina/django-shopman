"""Storefront context services.

Small, pure queries that collect contextual state used by storefront-facing
read paths (v1 views and the CatalogProjection builder):

- ``popular_skus`` — most-favourited SKUs across customer insights.
- ``happy_hour_state`` — current happy-hour window + discount percent.
- ``session_pricing_hints`` — fulfillment type + subtotal from the active
  cart session, matching what DiscountModifier sees at checkout.

These live under ``shopman.shop.services`` so both web views and the
projection layer consume them through a stable import path — no web-only
module reaches into another layer's private helpers.
"""

from __future__ import annotations

import logging
from datetime import time

from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone
from shopman.guestman.contrib.insights import InsightService

from shopman.shop.web.constants import STOREFRONT_CHANNEL_REF

logger = logging.getLogger(__name__)


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

    Only returns ``active=True`` when the instance has registered a modifier
    with code ``shop.happy_hour`` — the badge is never shown unless the
    discount will actually be applied at checkout. Settings-driven for now;
    a future iteration can move this to ``ChannelConfig``.
    """
    from shopman.orderman.registry import get_modifiers

    if not any(getattr(m, "code", None) == "shop.happy_hour" for m in get_modifiers()):
        return _HAPPY_HOUR_INACTIVE

    try:
        raw_start = getattr(settings, "SHOPMAN_HAPPY_HOUR_START", "16:00")
        raw_end = getattr(settings, "SHOPMAN_HAPPY_HOUR_END", "18:00")
        discount_percent = getattr(settings, "SHOPMAN_HAPPY_HOUR_DISCOUNT_PERCENT", 10)

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


def session_pricing_hints(request: HttpRequest | None) -> tuple[str, int]:
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
        ch = Channel.objects.filter(ref=STOREFRONT_CHANNEL_REF).first()
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
