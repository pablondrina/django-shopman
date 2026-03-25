from __future__ import annotations

from shopman.offering.models import ListingItem, Product
from shopman.utils.monetary import format_money

from ..constants import HAS_STOCKING, LISTING_REFS, STOREFRONT_CHANNEL_REF


def _get_price_q(product: Product) -> int | None:
    """Get price from first available listing, falling back to base_price_q."""
    for ref in LISTING_REFS:
        item = (
            ListingItem.objects.filter(
                listing__ref=ref,
                listing__is_active=True,
                product=product,
                is_published=True,
                is_available=True,
            )
            .order_by("-listing__priority")
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


def _annotate_products(products: list[Product]) -> list[dict]:
    """Build template-ready list with price, availability, and D-1 info."""
    d1_pct = _d1_discount_percent()
    result = []
    for p in products:
        price_q = _get_price_q(p)
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

        result.append({
            "product": p,
            "price_q": d1_price_q if is_d1 else price_q,
            "price_display": f"R$ {format_money(price_q)}" if price_q else None,
            "d1_price_display": d1_price_display,
            "original_price_display": f"R$ {format_money(price_q)}" if is_d1 and price_q else None,
            "is_d1": is_d1,
            "badge": badge,
            "availability": avail,
        })
    return result
