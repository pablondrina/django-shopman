"""Cart product context — read-side facade for the cart mutation path.

Resolves a product's listed price and D-1 flag for an add-to-cart intent.
A clean read facade (policy/data, no presentation), so it lives in the
orchestrator read-side (``shop/projections/``); the storefront cart intent
consumes it without ever reaching into the Core directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)


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
    qty: int = 1,
) -> CartProductContext | None:
    from shopman.offerman.models import Product

    product = Product.objects.filter(sku=sku, is_published=True).first()
    if not product:
        return None
    if not for_add:
        return CartProductContext(product=product, unit_price_q=0, is_d1=False)

    return CartProductContext(
        product=product,
        unit_price_q=_price_q(product, channel_ref=channel_ref, qty=qty) or 0,
        is_d1=_is_d1(product.sku, channel_ref=channel_ref),
    )


def _price_q(product, *, channel_ref: str, qty: int = 1) -> int | None:
    # Offerman é a autoridade de preço: `unit_price` faz o cascade correto por tier
    # (min_qty__lte=qty), respeita is_sellable e a janela de validade do listing, e
    # cai para base_price_q. Reimplementar aqui (ex.: order_by("-min_qty").first() sem
    # filtro de qty) cobrava o tier de atacado ao adicionar 1 unidade.
    from shopman.offerman.service import CatalogError, CatalogService

    try:
        return CatalogService.unit_price(
            product.sku, qty=Decimal(str(qty or 1)), listing=channel_ref
        )
    except CatalogError:
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
        logger.debug("cart_context._availability_for_sku degraded; using fallback", exc_info=True)
        return None
