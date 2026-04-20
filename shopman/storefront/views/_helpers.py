from __future__ import annotations

import logging
from datetime import date, time

from django.http import HttpRequest
from django.utils import timezone
from shopman.offerman.models import ListingItem, Product
from shopman.offerman.service import CatalogService
from shopman.utils.monetary import format_money

from shopman.storefront.services.storefront_context import (
    popular_skus,
    session_pricing_hints,
)

from ..constants import HAS_STOCKMAN, STOREFRONT_CHANNEL_REF

logger = logging.getLogger(__name__)


def _get_channel_listing_ref() -> str | None:
    """Ref da Listagem do canal web — por convenção, igual ao ref do canal."""
    try:
        from shopman.shop.models import Channel

        channel = Channel.objects.filter(ref=STOREFRONT_CHANNEL_REF).first()
        return channel.ref if channel else None
    except Exception as e:
        logger.warning("channel_listing_ref_failed: %s", e, exc_info=True)
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
            )
            .order_by("-min_qty")
            .first()
        )
        if item:
            return item.price_q
    return product.base_price_q


def _get_availability(sku: str, *, target_date: date | None = None) -> dict | None:
    """Breakdown de estoque para o canal storefront.

    **Listagem** (Listing / ListingItem + ``_published_products``): define o catálogo
    e o preço — se o SKU não está na listagem do canal, não entra no cardápio.

    **Disponibilidade** (aqui): quanto existe nas posições que esse canal pode usar,
    mesma regra do checkout — não substitui a listagem, só responde “tem físico?”
    """
    if not HAS_STOCKMAN:
        return None
    try:
        from shopman.stockman.services.availability import availability_for_sku

        from shopman.shop.adapters import stock as stock_adapter

        scope = stock_adapter.get_channel_scope(STOREFRONT_CHANNEL_REF)
        return availability_for_sku(
            sku,
            target_date=target_date,
            safety_margin=scope["safety_margin"],
            allowed_positions=scope["allowed_positions"],
            excluded_positions=scope.get("excluded_positions"),
        )
    except Exception as e:
        logger.warning("availability_lookup_failed sku=%s: %s", sku, e, exc_info=True)
        return None


def _line_item_is_d1(product: Product, *, listing_ref: str | None = None) -> bool:
    """True if SKU has only D-1 stock in its availability scope. POS internal use only."""
    avail = _get_availability(product.sku)
    if not avail:
        return False
    from decimal import Decimal

    breakdown = avail.get("breakdown", {})
    ready = breakdown.get("ready", Decimal("0"))
    in_prod = breakdown.get("in_production", Decimal("0"))
    d1 = breakdown.get("d1", Decimal("0"))
    return d1 > 0 and ready == 0 and in_prod == 0


def _to_storefront_avail(raw_avail: dict | None, product: Product) -> dict | None:
    """Convert raw availability_for_sku result to simplified storefront view.

    The storefront never consumes internal breakdown ({ready, in_production, d1}).
    Returns:
        {available_qty, can_order, is_paused, had_stock, state}
    or None if raw_avail is None.
    """
    if raw_avail is None:
        return None
    from decimal import Decimal

    is_paused = raw_avail.get("is_paused", False) or not product.is_sellable
    availability_policy = raw_avail.get("availability_policy", "planned_ok")
    total_promisable = raw_avail.get("total_promisable", Decimal("0"))
    can_order = ((availability_policy == "demand_ok") or total_promisable > 0) and not is_paused
    # had_stock: is_planned (future production scheduled) or currently available
    had_stock = can_order or raw_avail.get("is_planned", False) or total_promisable > 0
    state = _storefront_availability_state(
        can_order=can_order,
        had_stock=had_stock,
        is_paused=is_paused,
    )
    return {
        "available_qty": total_promisable,
        "can_order": can_order,
        "is_paused": is_paused,
        "had_stock": had_stock,
        "state": state,
        "availability_policy": availability_policy,
    }


def _storefront_availability_state(*, can_order: bool, had_stock: bool, is_paused: bool) -> str:
    """Map internal availability facts to the only UI states the storefront needs."""
    if can_order:
        return "available"
    if had_stock and not is_paused:
        return "sold_out"
    return "unavailable"


def _availability_badge(avail: dict | None, product: Product) -> dict:
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
    from shopman.storefront.models import Promotion
    from shopman.shop.modifiers import DiscountModifier

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


def _annotate_products(
    products: list[Product],
    listing_ref: str | None = None,
    popular_skus: set[str] | None = None,
    *,
    session_total_q: int | None = None,
    fulfillment_type: str | None = None,
    request: HttpRequest | None = None,
) -> list[dict]:
    """Build template-ready list with canonical price quote and availability."""
    if listing_ref is None:
        listing_ref = _get_channel_listing_ref()

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

    from shopman.offerman.models import CollectionItem

    skus = [p.sku for p in products]

    # ── Batch: collections per SKU ────────────────────────────────────────────
    sku_collections: dict[str, list[str]] = {}
    for ci in CollectionItem.objects.filter(product__sku__in=skus).select_related("collection"):
        sku_collections.setdefault(ci.product.sku, []).append(ci.collection.ref)

    # ── Batch: prices — one query for all SKUs ────────────────────────────────
    price_map: dict[str, int] = {}
    if listing_ref:
        for item in (
            ListingItem.objects.filter(
                listing__ref=listing_ref,
                listing__is_active=True,
                product__sku__in=skus,
                is_published=True,
                is_sellable=True,
            )
            .select_related("product")
            .order_by("-min_qty")
        ):
            price_map.setdefault(item.product.sku, item.price_q)

    # ── Batch: availability — one call for all SKUs ───────────────────────────
    avail_map: dict[str, dict | None] = {}
    if HAS_STOCKMAN:
        try:
            from shopman.stockman.services.availability import availability_for_skus

            from shopman.shop.adapters import stock as stock_adapter

            scope = stock_adapter.get_channel_scope(STOREFRONT_CHANNEL_REF)
            avail_map = availability_for_skus(
                skus,
                safety_margin=scope["safety_margin"],
                allowed_positions=scope["allowed_positions"],
                excluded_positions=scope.get("excluded_positions"),
            )
        except Exception as e:
            logger.warning("batch_availability_failed: %s", e, exc_info=True)

    result = []
    for p in products:
        base_q = price_map.get(p.sku) if listing_ref else None
        if base_q is None:
            base_q = p.base_price_q

        avail_raw = avail_map.get(p.sku)
        avail = _to_storefront_avail(avail_raw, p)
        badge = _availability_badge(avail, p)
        cols = sku_collections.get(p.sku, [])

        price = CatalogService.get_price(
            p.sku,
            qty=1,
            listing=listing_ref,
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


def _shop_status() -> dict:
    """
    Return shop open/closed status based on Shop.opening_hours.

    Returns dict: {is_open, opens_at, closes_at, message}
    """
    from shopman.shop.models import Shop

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
    from shopman.shop.models import Shop

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


def _hero_data(listing_ref: str | None = None, request: HttpRequest | None = None) -> dict | None:
    """
    Build hero section data: featured promotion or most popular product.

    Returns dict with keys: product, price_display, promo, image_url, badge
    or None if no suitable hero found.
    """
    try:
        from shopman.storefront.models import Promotion

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
            from shopman.offerman.models import Product as Prod

            product = Prod.objects.filter(sku=promo.skus[0], is_published=True).first()
            if product:
                price_q = _get_price_q(product, listing_ref=listing_ref)
                if promo.type == "percent":
                    discount_label = f"{promo.value}% OFF"
                else:
                    discount_label = f"R$ {format_money(promo.value)} OFF"
                cols: list[str] = []
                try:
                    from shopman.offerman.models import CollectionItem

                    cols = list(
                        CollectionItem.objects.filter(product=product).values_list(
                            "collection__ref", flat=True,
                        ),
                    )
                except Exception as e:
                    logger.warning("hero_data_collections_failed: %s", e, exc_info=True)
                    cols = []
                ft_hint, sub_hint = session_pricing_hints(request)
                disc_q, _ = _best_auto_promotion_discount_q(
                    promo.skus[0],
                    price_q or 0,
                    cols,
                    session_total_q=sub_hint,
                    fulfillment_type=ft_hint,
                )
                eff_q = (price_q or 0) - disc_q if price_q else None
                return {
                    "product": product,
                    "price_display": f"R$ {format_money(eff_q)}" if eff_q else None,
                    "original_price_display": f"R$ {format_money(price_q)}" if disc_q and price_q else None,
                    "promo_name": promo.name,
                    "discount_label": discount_label,
                    "image_url": product.image_url,
                    "sku": product.sku,
                }

        # Fallback: most popular product
        popular = popular_skus(limit=1)
        if popular:
            from shopman.offerman.models import Product as Prod

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
    except Exception as e:
        logger.warning("hero_data_failed: %s", e, exc_info=True)
    return None


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
