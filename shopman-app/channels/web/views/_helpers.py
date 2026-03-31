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


def _annotate_products(
    products: list[Product],
    listing_ref: str | None = None,
    popular_skus: set[str] | None = None,
) -> list[dict]:
    """Build template-ready list with price, availability, D-1 info, promotion badge, and popular flag."""
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
            "is_popular": popular_skus is not None and p.sku in popular_skus,
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


COLLECTION_EMOJIS: dict[str, str] = {
    "paes": "\U0001f956",       # 🥖
    "pao": "\U0001f956",
    "confeitaria": "\U0001f9c1",  # 🧁
    "doces": "\U0001f370",      # 🍰
    "cafes": "\u2615",          # ☕
    "cafe": "\u2615",
    "bebidas": "\U0001f964",    # 🥤
    "combos": "\U0001f4e6",     # 📦
    "salgados": "\U0001f950",   # 🥐
    "lanches": "\U0001f96a",    # 🥪
    "especiais": "\u2b50",      # ⭐
}


def _collection_emoji(slug: str) -> str:
    """Return emoji prefix for a collection slug, or empty string."""
    if not slug:
        return ""
    slug_lower = slug.lower()
    for key, emoji in COLLECTION_EMOJIS.items():
        if key in slug_lower:
            return emoji
    return ""


def _popular_skus(limit: int = 5) -> set[str]:
    """Aggregate favorite SKUs across all customer insights."""
    try:
        from shopman.customers.contrib.insights.models import CustomerInsight

        insights = CustomerInsight.objects.exclude(favorite_products=[]).values_list(
            "favorite_products", flat=True
        )[:200]
        sku_counts: dict[str, int] = {}
        for favorites in insights:
            if not favorites:
                continue
            for fav in favorites:
                sku = fav.get("sku", "") if isinstance(fav, dict) else str(fav)
                if sku:
                    sku_counts[sku] = sku_counts.get(sku, 0) + fav.get("qty", 1) if isinstance(fav, dict) else sku_counts.get(sku, 0) + 1
        if not sku_counts:
            return set()
        sorted_skus = sorted(sku_counts, key=sku_counts.get, reverse=True)
        return set(sorted_skus[:limit])
    except Exception:
        return set()


def _hero_data(listing_ref: str | None = None) -> dict | None:
    """
    Build hero section data: featured promotion or most popular product.

    Returns dict with keys: product, price_display, promo, image_url, badge
    or None if no suitable hero found.
    """
    try:
        from shop.models import Promotion

        now = timezone.now()
        promo = (
            Promotion.objects.filter(
                is_active=True,
                valid_from__lte=now,
                valid_until__gte=now,
            )
            .order_by("-valid_from")
            .first()
        )

        if promo and promo.skus:
            # Feature the first SKU of the promotion
            from shopman.offering.models import Product as Prod

            product = Prod.objects.filter(sku=promo.skus[0], is_published=True).first()
            if product:
                price_q = _get_price_q(product, listing_ref=listing_ref)
                if promo.type == "percent":
                    discount_label = f"{promo.value}% OFF"
                else:
                    discount_label = f"R$ {format_money(promo.value)} OFF"
                return {
                    "product": product,
                    "price_display": f"R$ {format_money(price_q)}" if price_q else None,
                    "promo_name": promo.name,
                    "discount_label": discount_label,
                    "image_url": product.image_url,
                    "sku": product.sku,
                }

        # Fallback: most popular product
        popular = _popular_skus(limit=1)
        if popular:
            from shopman.offering.models import Product as Prod

            sku = next(iter(popular))
            product = Prod.objects.filter(sku=sku, is_published=True).first()
            if product:
                price_q = _get_price_q(product, listing_ref=listing_ref)
                return {
                    "product": product,
                    "price_display": f"R$ {format_money(price_q)}" if price_q else None,
                    "promo_name": None,
                    "discount_label": None,
                    "image_url": product.image_url,
                    "sku": product.sku,
                }
    except Exception:
        pass
    return None


def _min_order_progress(subtotal_q: int, channel_ref: str = STOREFRONT_CHANNEL_REF) -> dict | None:
    """
    Calculate minimum order progress bar data.

    Returns dict with: minimum_q, remaining_q, percent, remaining_display, minimum_display
    or None if no minimum order configured or already met.
    """
    minimum_q = 0
    try:
        from shopman.ordering.models import Channel

        from channels.config import ChannelConfig

        channel = Channel.objects.filter(ref=channel_ref).first()
        if channel:
            config = ChannelConfig.effective(channel)
            if "shop.minimum_order" in config.rules.validators:
                raw = (channel.config or {}).get("rules", {}).get("minimum_order_q")
                if raw:
                    minimum_q = int(raw)
                else:
                    from shop.models import Shop

                    shop = Shop.load()
                    if shop and shop.defaults:
                        raw = shop.defaults.get("rules", {}).get("minimum_order_q")
                        if raw:
                            minimum_q = int(raw)
                    if not minimum_q:
                        from shop.validators import MINIMUM_ORDER_Q

                        minimum_q = MINIMUM_ORDER_Q
    except Exception:
        pass

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


def _upsell_suggestion(cart_skus: set[str], listing_ref: str | None = None) -> dict | None:
    """
    Return a single upsell product suggestion not already in the cart.

    Returns annotated product dict or None.
    """
    popular = _popular_skus(limit=10)
    candidates = [sku for sku in popular if sku not in cart_skus]
    if not candidates:
        return None

    from shopman.offering.models import Product as Prod

    for sku in candidates:
        product = Prod.objects.filter(sku=sku, is_published=True, is_available=True).first()
        if product:
            price_q = _get_price_q(product, listing_ref=listing_ref)
            return {
                "product": product,
                "price_display": f"R$ {format_money(price_q)}" if price_q else None,
                "sku": product.sku,
            }
    return None


def _cross_sell_products(sku: str, listing_ref: str | None = None, limit: int = 3) -> list[dict]:
    """
    Find products frequently bought together with the given SKU.

    Aggregates favorite_products from customers who have this SKU in their favorites.
    Returns annotated product dicts.
    """
    try:
        from shopman.customers.contrib.insights.models import CustomerInsight
        from shopman.offering.models import Product as Prod

        # Find customers who have this SKU in favorites
        insights = CustomerInsight.objects.filter(
            favorite_products__contains=[{"sku": sku}],
        ).values_list("favorite_products", flat=True)[:100]

        if not insights.exists():
            # Fallback: try text-based contains (JSONField varies by DB)
            insights = CustomerInsight.objects.exclude(
                favorite_products=[],
            ).values_list("favorite_products", flat=True)[:100]

        companion_counts: dict[str, int] = {}
        for favorites in insights:
            if not favorites:
                continue
            has_sku = any(
                (f.get("sku") if isinstance(f, dict) else str(f)) == sku
                for f in favorites
            )
            if not has_sku:
                continue
            for fav in favorites:
                fav_sku = fav.get("sku") if isinstance(fav, dict) else str(fav)
                if fav_sku and fav_sku != sku:
                    qty = fav.get("qty", 1) if isinstance(fav, dict) else 1
                    companion_counts[fav_sku] = companion_counts.get(fav_sku, 0) + qty

        if not companion_counts:
            return []

        top_skus = sorted(companion_counts, key=companion_counts.get, reverse=True)[:limit]
        products = list(Prod.objects.filter(sku__in=top_skus, is_published=True))
        if not products:
            return []
        return _annotate_products(products, listing_ref=listing_ref)
    except Exception:
        return []


def _allergen_info(product: Product) -> dict | None:
    """
    Extract allergen and dietary info from product.metadata.

    Returns dict with keys: allergens (list), dietary_info (list), serves (str|None)
    or None if no info available.
    """
    meta = getattr(product, "metadata", None)
    if not meta or not isinstance(meta, dict):
        return None

    allergens = meta.get("allergens", [])
    dietary = meta.get("dietary_info", [])
    serves = meta.get("serves")

    if not allergens and not dietary and not serves:
        return None

    return {
        "allergens": allergens if isinstance(allergens, list) else [],
        "dietary_info": dietary if isinstance(dietary, list) else [],
        "serves": str(serves) if serves else None,
    }


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
