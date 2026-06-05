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
from datetime import time, timedelta

from django.conf import settings
from django.utils import timezone
from shopman.guestman.contrib.insights import InsightService

logger = logging.getLogger(__name__)

DEFAULT_STOREFRONT_CHANNEL_REF = "web"
_FRESH_WINDOW_MINUTES_DEFAULT = 60  # "fresh from the oven" lookback fallback


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


def fresh_window_minutes() -> int:
    """Resolve the "fresh from the oven" window (minutes) from shop defaults.

    Shop-global policy (the lookup is not channel-scoped), mirroring how
    ``minimum_order_q`` lives in ``shop.defaults``. Defaults to 60.
    """
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        raw = (shop.defaults or {}).get("fresh_window_minutes") if shop else None
        return int(raw) if raw else _FRESH_WINDOW_MINUTES_DEFAULT
    except Exception:
        logger.debug("fresh_window_minutes degraded; using default", exc_info=True)
        return _FRESH_WINDOW_MINUTES_DEFAULT


def fresh_from_oven_skus(limit: int = 6) -> list[dict]:
    """SKUs that recently entered saleable stock from production — data only.

    Queries Stockman Moves created by ``StockPlanning.realize()`` — the
    credit side whose reason starts with "Recebido de produção" — within the
    configured fresh window (``fresh_window_minutes``).

    Returns a list of dicts ordered by most-recent first::

        [{"sku": "CROISSANT", "latest": datetime, "minutes_ago": 12.4}, ...]

    ``minutes_ago`` is the raw elapsed age; the Presentation buckets it (15-min
    rounding) and renders the freshness label. Returns an empty list when
    Stockman is unavailable or nothing was produced recently.
    """
    try:
        from django.db.models import Max, Sum
        from shopman.stockman.models import Move

        max_age_minutes = fresh_window_minutes()
        cutoff = timezone.now() - timedelta(minutes=max_age_minutes)
        rows = (
            Move.objects.filter(
                timestamp__gte=cutoff,
                quant__position__is_saleable=True,
                reason__istartswith="Recebido de produção",
                delta__gt=0,
            )
            .values("quant__sku")
            .annotate(latest=Max("timestamp"), total=Sum("delta"))
            .order_by("-latest")[:limit]
        )

        now = timezone.now()
        result = []
        for row in rows:
            minutes_ago = (now - row["latest"]).total_seconds() / 60
            if minutes_ago > max_age_minutes:
                continue
            result.append({
                "sku": row["quant__sku"],
                "latest": row["latest"],
                "minutes_ago": minutes_ago,
            })
        return result
    except Exception as e:
        logger.warning("fresh_from_oven_failed: %s", e, exc_info=True)
        return []


def happy_hour_state() -> dict:
    """Return the current happy-hour state.

    Only returns ``active=True`` when the instance has registered a modifier
    with code ``shop.happy_hour`` — the badge is never shown unless the
    discount will actually be applied at checkout.

    Reads window/percent from ``RuleConfig "happy_hour"`` — the **same source**
    the ``HappyHourModifier`` reads for the actual discount — so the badge and
    the applied discount can never diverge. Falls back to ``SHOPMAN_HAPPY_HOUR_*``
    settings, then to defaults, mirroring the modifier's resolution chain.
    """
    from shopman.orderman.registry import get_modifiers

    if not any(getattr(m, "code", None) == "shop.happy_hour" for m in get_modifiers()):
        return _HAPPY_HOUR_INACTIVE

    try:
        from shopman.shop.rules.engine import get_rule_params

        params = get_rule_params("happy_hour")
        raw_start = params.get("start") or getattr(settings, "SHOPMAN_HAPPY_HOUR_START", "16:00")
        raw_end = params.get("end") or getattr(settings, "SHOPMAN_HAPPY_HOUR_END", "18:00")
        discount_percent = params.get(
            "discount_percent",
            getattr(settings, "SHOPMAN_HAPPY_HOUR_DISCOUNT_PERCENT", 10),
        )

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
