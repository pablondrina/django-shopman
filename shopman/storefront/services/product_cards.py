from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from django.http import HttpRequest
from django.utils import timezone
from shopman.utils.monetary import format_money

from shopman.shop.services import catalog_context
from shopman.shop.services.storefront_context import session_pricing_hints

from ..constants import STOREFRONT_CHANNEL_REF

logger = logging.getLogger(__name__)


def get_channel_listing_ref() -> str | None:
    """Ref da Listagem do canal web — por convenção, igual ao ref do canal."""
    try:
        from shopman.shop.models import Channel

        channel = Channel.objects.filter(ref=STOREFRONT_CHANNEL_REF).first()
        return channel.ref if channel else None
    except Exception as e:
        logger.warning("channel_listing_ref_failed: %s", e, exc_info=True)
        return None


def get_price_q(product: Any, listing_ref: str | None = None) -> int | None:
    """Get price from channel listing, falling back to base_price_q."""
    if listing_ref is None:
        listing_ref = get_channel_listing_ref()
    if listing_ref:
        price_q = catalog_context.listing_price_for_product(product, listing_ref)
        if price_q is not None:
            return price_q
    return product.base_price_q


def get_availability(sku: str, *, target_date: date | None = None) -> dict | None:
    """Breakdown de estoque para o canal storefront.

    **Listagem** (Listing / ListingItem + ``_published_products``): define o catálogo
    e o preço — se o SKU não está na listagem do canal, não entra no cardápio.

    **Disponibilidade** (aqui): quanto existe nas posições que esse canal pode usar,
    mesma regra do checkout — não substitui a listagem, só responde “tem físico?”
    """
    return catalog_context.availability_for_sku(
        sku,
        channel_ref=STOREFRONT_CHANNEL_REF,
        target_date=target_date,
    )


def line_item_is_d1(product: Any, *, listing_ref: str | None = None) -> bool:
    """True if SKU has only D-1 stock in its availability scope. POS internal use only."""
    avail = get_availability(product.sku)
    if not avail:
        return False
    breakdown = avail.get("breakdown", {})
    ready = breakdown.get("ready", Decimal("0"))
    in_prod = breakdown.get("in_production", Decimal("0"))
    d1 = breakdown.get("d1", Decimal("0"))
    return d1 > 0 and ready == 0 and in_prod == 0


def _to_storefront_avail(raw_avail: dict | None, product: Any) -> dict | None:
    """Convert raw availability_for_sku result to simplified storefront view.

    The storefront never consumes internal breakdown ({ready, in_production, d1}).
    Returns:
        {available_qty, can_order, is_paused, had_stock, state}
    or None if raw_avail is None.
    """
    return catalog_context.storefront_availability(raw_avail, is_sellable=product.is_sellable)


def _storefront_availability_state(*, can_order: bool, had_stock: bool, is_paused: bool) -> str:
    """Map internal availability facts to the only UI states the storefront needs."""
    if can_order:
        return "available"
    if had_stock and not is_paused:
        return "sold_out"
    return "unavailable"


def _availability_badge(avail: dict | None, product: Any) -> dict:
    """
    Determine the availability badge for a product.

    ``avail`` must be the simplified storefront format from ``_to_storefront_avail()``,
    NOT the raw breakdown from availability_for_sku(). Returns:
      {label, css_class, can_add_to_cart}

    Customer-facing states (AVAILABILITY-PLAN vocabulary):
    - available: can_order=True → no badge (implicit)
    - qualquer caso de can_order=False (paused, sold-out, etc.) → "Indisponível"
    """
    if not product.is_sellable:
        return {"label": "Indisponível", "css_class": "badge-unavailable", "can_add_to_cart": False}

    if avail is None:
        # No stockman module — fall back to product.is_sellable flag
        return {"label": "", "css_class": "", "can_add_to_cart": product.is_sellable}

    state = avail.get("state") or _storefront_availability_state(
        can_order=avail.get("can_order", True),
        had_stock=avail.get("had_stock", False),
        is_paused=avail.get("is_paused", False),
    )
    if state == "available":
        return {"label": "", "css_class": "badge-available", "can_add_to_cart": True}
    return {"label": "Indisponível", "css_class": "badge-unavailable", "can_add_to_cart": False}


def _promo_matches_for_vitrine(promo, sku: str, ctx: dict) -> bool:
    """Igual DiscountModifier._matches, mas se não há fulfillment na sessão e a promo exige tipo,
    testa cada tipo permitido para ainda exibir preço/badge no cardápio."""
    from shopman.shop.modifiers import DiscountModifier

    if not promo.fulfillment_types:
        return DiscountModifier._matches(promo, sku, ctx)
    ft = (ctx.get("fulfillment_type") or "").strip()
    if ft:
        return DiscountModifier._matches(promo, sku, ctx)
    for try_ft in promo.fulfillment_types:
        c = {**ctx, "fulfillment_type": try_ft}
        if DiscountModifier._matches(promo, sku, c):
            return True
    return False



def _best_auto_promotion_discount_q(
    sku: str,
    price_q: int,
    sku_collections: list[str],
    *,
    session_total_q: int = 0,
    fulfillment_type: str = "",
):
    """Maior desconto entre promoções automáticas (igual DiscountModifier), para o vitrine.

    Passe ``fulfillment_type`` e ``session_total_q`` da sessão do carrinho
    (``services.storefront_context.session_pricing_hints``) para coincidir
    com o que o modificador aplica no checkout.
    """
    from shopman.shop.modifiers import DiscountModifier
    from shopman.storefront.models import Promotion

    now = timezone.now()
    promotions = list(
        Promotion.objects.filter(
            is_active=True,
            valid_from__lte=now,
            valid_until__gte=now,
        ).exclude(coupons__isnull=False)
    )
    ctx = {
        "fulfillment_type": fulfillment_type or "",
        "sku_collections": {sku: sku_collections},
        "customer_segment": "",
        "customer_group": "",
    }
    best_discount_q = 0
    best_promo = None
    for promo in promotions:
        if promo.min_order_q and session_total_q < promo.min_order_q:
            continue
        if not _promo_matches_for_vitrine(promo, sku, ctx):
            continue
        discount_q = DiscountModifier._calc_discount(promo, price_q)
        if discount_q > best_discount_q:
            best_discount_q = discount_q
            best_promo = promo
    return best_discount_q, best_promo


def annotate_products(
    products: list[Any],
    listing_ref: str | None = None,
    popular_skus: set[str] | None = None,
    *,
    session_total_q: int | None = None,
    fulfillment_type: str | None = None,
    request: HttpRequest | None = None,
) -> list[dict]:
    """Build template-ready list with canonical price quote and availability."""
    if listing_ref is None:
        listing_ref = get_channel_listing_ref()

    if request is not None and (session_total_q is None or fulfillment_type is None):
        ft_hint, sub_hint = session_pricing_hints(request)
        if fulfillment_type is None:
            fulfillment_type = ft_hint
        if session_total_q is None:
            session_total_q = sub_hint
    if session_total_q is None:
        session_total_q = 0
    if fulfillment_type is None:
        fulfillment_type = ""

    skus = [p.sku for p in products]

    # ── Batch: collections per SKU ────────────────────────────────────────────
    sku_collections = catalog_context.collection_refs_by_sku(skus)

    # ── Batch: prices — one query for all SKUs ────────────────────────────────
    price_map: dict[str, int] = {}
    if listing_ref:
        price_map = catalog_context.listing_price_map(skus, listing_ref)

    # ── Batch: availability — one call for all SKUs ───────────────────────────
    avail_map = catalog_context.availability_for_skus(skus, channel_ref=STOREFRONT_CHANNEL_REF)

    result = []
    for p in products:
        base_q = price_map.get(p.sku) if listing_ref else None
        if base_q is None:
            base_q = p.base_price_q

        avail_raw = avail_map.get(p.sku)
        avail = _to_storefront_avail(avail_raw, p)
        badge = _availability_badge(avail, p)
        cols = sku_collections.get(p.sku, [])

        price = catalog_context.contextual_price(
            p.sku,
            qty=1,
            listing_ref=listing_ref,
            context={
                "sku_collections": cols,
                "session_total_q": session_total_q,
                "fulfillment_type": fulfillment_type,
            },
            list_unit_price_q=base_q,
        )

        promo_badge = None
        promo_price_display = None
        promo_original_price_display = None
        has_promo_price = False

        if price.adjustments:
            has_promo_price = price.final_unit_price_q < price.list_unit_price_q
            adjustment = price.adjustments[0]
            if has_promo_price:
                promo_price_display = f"R$ {format_money(price.final_unit_price_q)}"
                promo_original_price_display = f"R$ {format_money(price.list_unit_price_q)}"
                promo_badge = {
                    "name": adjustment.metadata.get("promotion_name", adjustment.label),
                    "type": adjustment.metadata.get("promotion_type"),
                    "value": adjustment.metadata.get("promotion_value"),
                    "label": adjustment.metadata.get("badge_label", adjustment.label),
                }

        effective_q = price.final_unit_price_q
        price_display = f"R$ {format_money(effective_q)}" if effective_q else None

        # available_qty for stepper clamp (WP-AV-07). None when Stockman
        # hasn't reported a number (untracked SKU or demand_ok policy).
        available_qty = None
        if avail_raw is not None:
            total = avail_raw.get("total_promisable")
            if total is not None:
                try:
                    from decimal import Decimal as _D
                    available_qty = int(_D(str(total)))
                except Exception:
                    available_qty = None

        result.append({
            "product": p,
            "price_q": effective_q,
            "price_display": price_display,
            "badge": badge,
            "availability": avail,
            "available_qty": available_qty,
            "promo_badge": promo_badge,
            "has_promo_price": has_promo_price,
            "promo_price_display": promo_price_display,
            "promo_original_price_display": promo_original_price_display,
            "is_popular": popular_skus is not None and p.sku in popular_skus,
        })
    return result
