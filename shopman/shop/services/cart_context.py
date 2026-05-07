"""Cart product context resolved through orchestrator services."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CartProductContext:
    product: object
    unit_price_q: int
    is_d1: bool


def product_context(
    sku: str,
    *,
    channel_ref: str = "web",
    for_add: bool = True,
) -> CartProductContext | None:
    from shopman.offerman.models import Product

    product = Product.objects.filter(sku=sku, is_published=True).first()
    if not product:
        return None
    if not for_add:
        return CartProductContext(product=product, unit_price_q=0, is_d1=False)

    return CartProductContext(
        product=product,
        unit_price_q=_price_q(product, channel_ref=channel_ref) or 0,
        is_d1=_is_d1(product.sku, channel_ref=channel_ref),
    )


def _price_q(product, *, channel_ref: str) -> int | None:
    from shopman.offerman.models import ListingItem

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
    if item:
        return item.price_q
    return product.base_price_q


def _is_d1(sku: str, *, channel_ref: str) -> bool:
    avail = _availability_for_sku(sku, channel_ref=channel_ref)
    if not avail:
        return False

    breakdown = avail.get("breakdown", {})
    ready = breakdown.get("ready", Decimal("0"))
    in_prod = breakdown.get("in_production", Decimal("0"))
    d1 = breakdown.get("d1", Decimal("0"))
    return d1 > 0 and ready == 0 and in_prod == 0


def _availability_for_sku(sku: str, *, channel_ref: str) -> dict | None:
    try:
        from shopman.stockman.services.availability import availability_for_sku

        from shopman.shop.adapters import stock as stock_adapter

        scope = stock_adapter.get_channel_scope(channel_ref)
        return availability_for_sku(
            sku,
            safety_margin=scope["safety_margin"],
            allowed_positions=scope["allowed_positions"],
            excluded_positions=scope.get("excluded_positions"),
        )
    except Exception:
        return None
