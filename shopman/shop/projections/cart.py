"""Cart read-side projections — semantic data, surface-agnostic.

Holds the policy-laden cart data the orchestrator resolves for any surface:
the minimum-order progress (cents, no copy) and the upsell suggestion
(refs + cents, no rendered price, no model instance). Presentation —
``R$`` formatting, "Faltam X" copy — lives in ``<surface>/presentation/``.

These were drained out of ``services/storefront_context`` so the storefront
presentation no longer reaches into the write-side for read data (ADR-014,
rule R-A). The richer cart projection (lines, totals, ``can_checkout``,
actions) follows when ``CartService.get_cart`` is retired in WP6/D1.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DEFAULT_STOREFRONT_CHANNEL_REF = "web"
_MINIMUM_ORDER_Q_DEFAULT = 1000  # R$ 10,00 fallback when the rule is active


@dataclass(frozen=True)
class MinimumOrderProgressProjection:
    """Progress toward the channel's minimum-order amount — cents only.

    ``percent`` is the integer share of the minimum already reached (0–100).
    The presentation derives the ``R$`` strings and the "Faltam X" copy.
    """

    minimum_q: int
    remaining_q: int
    percent: int


@dataclass(frozen=True)
class UpsellSuggestionProjection:
    """One popular SKU not yet in the cart, offered as an upsell.

    Carries the resolved listed price (``unit_price_q``) the checkout would
    charge plus the name/image the surface needs to render — no Django model
    instance, no formatted price.
    """

    sku: str
    name: str
    unit_price_q: int
    image_url: str | None


def build_minimum_order_progress(
    subtotal_q: int,
    channel_ref: str = DEFAULT_STOREFRONT_CHANNEL_REF,
) -> MinimumOrderProgressProjection | None:
    """Progress toward the minimum order amount configured for ``channel_ref``.

    Returns ``None`` when the channel does not activate the
    ``shop.minimum_order`` validator, or when the subtotal already meets the
    minimum. Keeps the rule lookup out of every surface so the cart, checkout
    and live cart-mutation payloads consume identical guidance.
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
    return MinimumOrderProgressProjection(
        minimum_q=minimum_q,
        remaining_q=remaining_q,
        percent=percent,
    )


def build_upsell_suggestion(
    cart_skus: set[str],
    *,
    channel_ref: str = DEFAULT_STOREFRONT_CHANNEL_REF,
) -> UpsellSuggestionProjection | None:
    """Return one popular SKU not already in ``cart_skus`` (or ``None``).

    Resolves the listed price via ``ListingItem`` so the suggestion carries
    the same price the checkout would charge.
    """
    from shopman.offerman.models import ListingItem, Product

    from shopman.shop.projections.storefront_context import popular_skus

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
        return UpsellSuggestionProjection(
            sku=product.sku,
            name=getattr(product, "name", "") or "",
            unit_price_q=int(price_q or 0),
            image_url=getattr(product, "image_url", None) or None,
        )
    return None


__all__ = [
    "MinimumOrderProgressProjection",
    "UpsellSuggestionProjection",
    "build_minimum_order_progress",
    "build_upsell_suggestion",
]
