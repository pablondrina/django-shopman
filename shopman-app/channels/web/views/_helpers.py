from __future__ import annotations

from datetime import time

from django.utils import timezone
from shopman.offering.models import ListingItem, Product
from shopman.utils.monetary import format_money

from ..constants import HAS_STOCKING, STOREFRONT_CHANNEL_REF


def _get_channel_listing_ref() -> str | None:
    """Get the listing_ref for the storefront channel."""
    try:
        from shopman.ordering.models import Channel

        channel = Channel.objects.filter(ref=STOREFRONT_CHANNEL_REF).first()
        return channel.listing_ref if channel else None
    except Exception:
        return None


def _get_price_q(product: Product, listing_ref: str | None = None) -> int | None:
    """Get price from channel listing, falling back to base_price_q."""
    if listing_ref is None:
        listing_ref = _get_channel_listing_ref()
    if listing_ref:
        item = (
            ListingItem.objects.filter(
                listing__ref=listing_ref,
                listing__is_active=True,
                product=product,
                is_published=True,
                is_available=True,
            )
            .order_by("-min_qty")
            .first()
        )
        if item:
            return item.price_q
    return product.base_price_q


def _get_availability(sku: str) -> dict | None:
    """Get availability breakdown for a SKU. Returns None if stocking unavailable."""
    if not HAS_STOCKING:
        return None
    try:
        from shopman.stocking.api.views import _availability_for_sku, _get_safety_margin

        margin = _get_safety_margin(STOREFRONT_CHANNEL_REF)
        return _availability_for_sku(sku, safety_margin=margin)
    except Exception:
        return None


def _availability_badge(avail: dict | None, product: Product) -> dict:
    """
    Determine the availability badge for a product.

    Returns dict with keys: label, css_class, can_add_to_cart.
    Possible states:
    - available: ready stock > 0
    - preparing: no ready stock, but in_production > 0
    - d1_only: only D-1 stock (yesterday's leftovers)
    - sold_out: no stock at all
    - paused: product marked unavailable by admin
    - unknown: stocking unavailable (fall back to product.is_available)
    """
    if not product.is_available:
        return {"label": "Indisponível", "css_class": "badge-paused", "can_add_to_cart": False}

    if avail is None:
        # No stocking — fall back to product.is_available flag
        return {"label": "", "css_class": "", "can_add_to_cart": product.is_available}

    if avail.get("is_paused"):
        return {"label": "Indisponível", "css_class": "badge-paused", "can_add_to_cart": False}

    breakdown = avail.get("breakdown", {})
    from decimal import Decimal

    ready = breakdown.get("ready", Decimal("0"))
    in_prod = breakdown.get("in_production", Decimal("0"))
    d1 = breakdown.get("d1", Decimal("0"))

    if ready > 0:
        return {"label": "Disponível", "css_class": "badge-available", "can_add_to_cart": True}
    if in_prod > 0:
        return {"label": "Preparando...", "css_class": "badge-preparing", "can_add_to_cart": True}
    if d1 > 0:
        return {"label": "Últimas unidades", "css_class": "badge-d1", "can_add_to_cart": True}
    if avail.get("is_planned"):
        return {"label": "Em breve", "css_class": "badge-planned", "can_add_to_cart": False}
    return {"label": "Esgotado", "css_class": "badge-sold-out", "can_add_to_cart": False}


def _d1_discount_percent() -> int:
    """Get D-1 discount percent from channel config or default."""
    from shop.modifiers import D1_DISCOUNT_PERCENT

    try:
        from shopman.ordering.models import Channel

        channel = Channel.objects.filter(ref=STOREFRONT_CHANNEL_REF).first()
        if channel and channel.config:
            return channel.config.get("rules", {}).get("d1_discount_percent", D1_DISCOUNT_PERCENT)
    except Exception:
        pass
    return D1_DISCOUNT_PERCENT


def _annotate_products(products: list[Product], listing_ref: str | None = None) -> list[dict]:
    """Build template-ready list with price, availability, D-1 info, and promotion badge."""
    if listing_ref is None:
        listing_ref = _get_channel_listing_ref()
    d1_pct = _d1_discount_percent()

    # Pre-load active promotions for badge annotation
    promo_map = _active_promotions_for_products(products)

    result = []
    for p in products:
        price_q = _get_price_q(p, listing_ref=listing_ref)
        avail = _get_availability(p.sku)
        badge = _availability_badge(avail, p)

        d1_price_q = None
        d1_price_display = None
        is_d1 = False
        if avail and badge["css_class"] == "badge-d1" and price_q:
            is_d1 = True
            from shopman.utils.monetary import monetary_div

            discount_q = monetary_div(price_q * d1_pct, 100)
            d1_price_q = price_q - discount_q
            d1_price_display = f"R$ {format_money(d1_price_q)}"

        # Promotion badge (only if not already D-1 discounted)
        promo_badge = None
        if not is_d1 and p.sku in promo_map:
            promo_badge = promo_map[p.sku]

        result.append({
            "product": p,
            "price_q": d1_price_q if is_d1 else price_q,
            "price_display": f"R$ {format_money(price_q)}" if price_q else None,
            "d1_price_display": d1_price_display,
            "original_price_display": f"R$ {format_money(price_q)}" if is_d1 and price_q else None,
            "is_d1": is_d1,
            "badge": badge,
            "availability": avail,
            "promo_badge": promo_badge,
        })
    return result


def _shop_status() -> dict:
    """
    Return shop open/closed status based on Shop.opening_hours.

    Returns dict: {is_open, opens_at, closes_at, message}
    """
    from shop.models import Shop

    shop = Shop.load()
    if not shop or not shop.opening_hours:
        return {"is_open": True, "opens_at": None, "closes_at": None, "message": ""}

    now = timezone.localtime()
    day_name = now.strftime("%A").lower()  # "monday", "tuesday", ...
    hours = shop.opening_hours.get(day_name)

    if not hours or not hours.get("open") or not hours.get("close"):
        return {"is_open": False, "opens_at": None, "closes_at": None, "message": "Fechado hoje"}

    open_time = time.fromisoformat(hours["open"])
    close_time = time.fromisoformat(hours["close"])
    current_time = now.time()

    if open_time <= current_time < close_time:
        close_str = hours["close"].replace(":", "h", 1)
        # Warn if closing within 1 hour
        from datetime import datetime, timedelta

        close_dt = datetime.combine(now.date(), close_time, tzinfo=now.tzinfo)
        remaining = close_dt - now
        if remaining <= timedelta(hours=1):
            return {
                "is_open": True,
                "opens_at": hours["open"],
                "closes_at": hours["close"],
                "message": f"Fechamos às {close_str}",
            }
        return {
            "is_open": True,
            "opens_at": hours["open"],
            "closes_at": hours["close"],
            "message": f"Aberto até {close_str}",
        }

    # Closed now — find next opening
    open_str = hours["open"].replace(":", "h", 1)
    if current_time < open_time:
        return {
            "is_open": False,
            "opens_at": hours["open"],
            "closes_at": hours["close"],
            "message": f"Fechado — abrimos às {open_str}",
        }
    # After closing time today
    return {
        "is_open": False,
        "opens_at": hours["open"],
        "closes_at": hours["close"],
        "message": "Fechado — até amanhã!",
    }


DAY_NAMES_PT = {
    "monday": "Segunda",
    "tuesday": "Terça",
    "wednesday": "Quarta",
    "thursday": "Quinta",
    "friday": "Sexta",
    "saturday": "Sábado",
    "sunday": "Domingo",
}

DAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _format_opening_hours() -> list[dict]:
    """
    Format Shop.opening_hours into display-ready lines for templates.

    Groups consecutive days with the same hours into ranges.
    Returns list of {label, hours} dicts, e.g.:
      [{"label": "Terça a Sábado", "hours": "7h — 19h"},
       {"label": "Domingo", "hours": "7h — 13h"},
       {"label": "Segunda", "hours": "Fechado"}]
    """
    from shop.models import Shop

    shop = Shop.load()
    if not shop or not shop.opening_hours:
        return []

    def _fmt_time(t: str) -> str:
        """'06:00' -> '6h', '20:00' -> '20h', '07:30' -> '7h30'."""
        parts = t.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        if m:
            return f"{h}h{m:02d}"
        return f"{h}h"

    # Build (day, hours_str) pairs in order
    day_hours: list[tuple[str, str]] = []
    for day in DAY_ORDER:
        info = shop.opening_hours.get(day)
        if info and info.get("open") and info.get("close"):
            day_hours.append((day, f"{_fmt_time(info['open'])} — {_fmt_time(info['close'])}"))
        else:
            day_hours.append((day, "Fechado"))

    # Group consecutive days with same hours
    groups: list[tuple[list[str], str]] = []
    for day, hours in day_hours:
        if groups and groups[-1][1] == hours:
            groups[-1][0].append(day)
        else:
            groups.append(([day], hours))

    result = []
    for days, hours in groups:
        if len(days) == 1:
            label = DAY_NAMES_PT[days[0]]
        elif len(days) == 2:
            label = f"{DAY_NAMES_PT[days[0]]} e {DAY_NAMES_PT[days[1]]}"
        else:
            label = f"{DAY_NAMES_PT[days[0]]} a {DAY_NAMES_PT[days[-1]]}"
        result.append({"label": label, "hours": hours})

    return result


CARRIER_TRACKING_URLS: dict[str, str] = {
    "correios": "https://rastreamento.correios.com.br/?objetos={code}",
    "jadlog": "https://www.jadlog.com.br/tracking?code={code}",
}


def _carrier_tracking_url(carrier: str, tracking_code: str) -> str | None:
    """
    Build a tracking URL for known carriers.

    Returns URL string or None if carrier is unknown or tracking_code is empty.
    """
    if not carrier or not tracking_code:
        return None
    template = CARRIER_TRACKING_URLS.get(carrier.lower())
    if template:
        return template.format(code=tracking_code)
    return None


def _active_promotions_for_products(products: list[Product]) -> dict[str, dict]:
    """
    Return a map of SKU -> promotion badge info for products covered by active promotions.

    Badge info: {name, type, value, label}
    """
    try:
        from shop.models import Promotion

        now = timezone.now()
        promotions = list(
            Promotion.objects.filter(
                is_active=True,
                valid_from__lte=now,
                valid_until__gte=now,
            )
        )
        if not promotions:
            return {}

        # Build SKU -> collection slugs map
        from shopman.offering.models import CollectionItem

        skus = [p.sku for p in products]
        sku_collections: dict[str, list[str]] = {}
        for ci in CollectionItem.objects.filter(product__sku__in=skus).select_related("collection"):
            sku_collections.setdefault(ci.product.sku, []).append(ci.collection.slug)

        result: dict[str, dict] = {}
        for p in products:
            for promo in promotions:
                # Skip fulfillment-specific promos in catalog (no context yet)
                if promo.fulfillment_types:
                    continue
                if promo.skus and p.sku not in promo.skus:
                    continue
                if promo.collections:
                    p_cols = sku_collections.get(p.sku, [])
                    if not any(c in promo.collections for c in p_cols):
                        continue
                # Match found
                if promo.type == "percent":
                    label = f"-{promo.value}%"
                else:
                    label = f"-R$ {format_money(promo.value)}"
                result[p.sku] = {
                    "name": promo.name,
                    "type": promo.type,
                    "value": promo.value,
                    "label": label,
                }
                break  # First matching promo wins
        return result
    except Exception:
        return {}
