"""Storefront context services.

Small, pure queries that collect contextual state used by storefront-facing
read paths (v1 views and projection builders):

- ``popular_skus`` — most-favourited SKUs across customer insights.
- ``happy_hour_state`` — current happy-hour window + discount percent.
- ``session_pricing_hints`` — fulfillment type + subtotal from the active
  cart session, matching what DiscountModifier sees at checkout.
- ``minimum_order_progress`` — progress bar data for minimum-order rule.
- ``upsell_suggestion`` — one popular SKU not yet in the cart.

These live under ``shopman.shop.services`` so both web views and the
projection layer consume them through a stable import path — no web-only
module reaches into another layer's private helpers.
"""

from __future__ import annotations

import logging
import math
from datetime import time, timedelta

from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone
from shopman.guestman.contrib.insights import InsightService
from shopman.offerman.models import ListingItem, Product
from shopman.utils.monetary import format_money

from shopman.shop.web.constants import STOREFRONT_CHANNEL_REF

logger = logging.getLogger(__name__)

_MINIMUM_ORDER_Q_DEFAULT = 1000  # R$ 10,00 fallback when the rule is active


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


def fresh_from_oven_skus(limit: int = 6, max_age_minutes: int = 60) -> list[dict]:
    """SKUs that recently entered saleable stock from production.

    Queries Stockman Moves created by ``StockPlanning.realize()`` — the
    credit side whose reason starts with "Recebido de produção".

    Returns a list of dicts ordered by most-recent first::

        [{"sku": "CROISSANT", "latest": datetime, "freshness_label": "há 15 min"}, ...]

    Freshness labels are rounded UP to the nearest 15-minute interval,
    capped at 1 h (``max_age_minutes``). Returns an empty list when
    Stockman is unavailable or nothing was produced recently.
    """
    try:
        from django.db.models import Max, Sum
        from shopman.stockman.models import Move

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
            elapsed = now - row["latest"]
            minutes = elapsed.total_seconds() / 60
            if minutes > max_age_minutes:
                continue
            bucket = min(math.ceil(minutes / 15) * 15, 60)
            if bucket <= 0:
                bucket = 15
            label = "há 1h" if bucket >= 60 else f"há {bucket} min"
            result.append({
                "sku": row["quant__sku"],
                "latest": row["latest"],
                "freshness_label": label,
            })
        return result
    except Exception as e:
        logger.warning("fresh_from_oven_failed: %s", e, exc_info=True)
        return []


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


def minimum_order_progress(
    subtotal_q: int, channel_ref: str = STOREFRONT_CHANNEL_REF,
) -> dict | None:
    """Progress toward the minimum order amount configured for ``channel_ref``.

    Returns a dict with ``minimum_q``, ``remaining_q``, ``percent``,
    ``remaining_display`` and ``minimum_display``. Returns ``None`` when:

    - the channel does not activate the ``shop.minimum_order`` validator, OR
    - the current subtotal already meets the minimum.

    Keeps the rule lookup out of the view layer so both v1 helpers and the
    CartProjection builder can consume identical guidance.
    """
    minimum_q = 0
    try:
        from shopman.shop.config import ChannelConfig
        from shopman.shop.models import Channel, Shop

        channel = Channel.objects.filter(ref=channel_ref).first()
        if channel:
            rules = ChannelConfig.for_channel(channel).rules
            if rules.validators is None or "shop.minimum_order" in rules.validators:
                shop = Shop.load()
                raw = (
                    shop.defaults.get("rules", {}).get("minimum_order_q")
                    if shop and shop.defaults
                    else None
                )
                minimum_q = int(raw) if raw else _MINIMUM_ORDER_Q_DEFAULT
    except Exception as e:
        logger.warning("min_order_progress_failed: %s", e, exc_info=True)

    if not minimum_q or subtotal_q >= minimum_q:
        return None

    remaining_q = minimum_q - subtotal_q
    percent = int(min(subtotal_q * 100 / minimum_q, 100)) if minimum_q else 0
    return {
        "minimum_q": minimum_q,
        "remaining_q": remaining_q,
        "percent": percent,
        "remaining_display": f"R$ {format_money(remaining_q)}",
        "minimum_display": f"R$ {format_money(minimum_q)}",
    }


def upsell_suggestion(
    cart_skus: set[str],
    *,
    channel_ref: str = STOREFRONT_CHANNEL_REF,
) -> dict | None:
    """Return one popular SKU not already in ``cart_skus`` (or ``None``).

    Resolves the listed price for the picked product via ``ListingItem`` so
    the suggestion renders with the same price the checkout would charge.
    Shape matches what ``cart_drawer.html`` expects today: a dict with
    ``product`` (the Django instance, for icon/name lookup), ``sku`` and
    ``price_display``.
    """
    popular = popular_skus(limit=10)
    candidates = [sku for sku in popular if sku not in cart_skus]
    if not candidates:
        return None

    for sku in candidates:
        product = Product.objects.filter(
            sku=sku, is_published=True, is_sellable=True,
        ).first()
        if product is None:
            continue
        item = (
            ListingItem.objects.filter(
                listing__ref=channel_ref,
                listing__is_active=True,
                product=product,
                is_published=True,
            )
            .order_by("-min_qty")
            .first()
        )
        price_q = item.price_q if item else product.base_price_q
        return {
            "product": product,
            "sku": product.sku,
            "price_q": price_q,
            "price_display": f"R$ {format_money(price_q)}" if price_q else None,
        }
    return None


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
