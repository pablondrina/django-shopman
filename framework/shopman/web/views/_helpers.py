from __future__ import annotations

import logging
from datetime import time

from django.http import HttpRequest
from django.utils import timezone

from shopman.offering.models import ListingItem, Product
from shopman.utils.monetary import format_money

from ..constants import HAS_STOCKING, STOREFRONT_CHANNEL_REF

logger = logging.getLogger(__name__)


def _get_channel_listing_ref() -> str | None:
    """Ref da Listagem do canal web (`Channel.listing_ref`) — catálogo e preço ofertados."""
    try:
        from shopman.ordering.models import Channel

        channel = Channel.objects.filter(ref=STOREFRONT_CHANNEL_REF).first()
        return channel.listing_ref if channel else None
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
                is_available=True,
            )
            .order_by("-min_qty")
            .first()
        )
        if item:
            return item.price_q
    return product.base_price_q


def _get_availability(sku: str) -> dict | None:
    """Breakdown de estoque para o canal storefront.

    **Listagem** (Listing / ListingItem + ``_published_products``): define o catálogo
    e o preço — se o SKU não está na listagem do canal, não entra no cardápio.

    **Disponibilidade** (aqui): quanto existe nas posições que esse canal pode usar,
    mesma regra do checkout — não substitui a listagem, só responde “tem físico?”
    """
    if not HAS_STOCKING:
        return None
    try:
        from shopman.stocking.services.availability import (
            availability_for_sku,
            availability_scope_for_channel,
        )

        scope = availability_scope_for_channel(STOREFRONT_CHANNEL_REF)
        return availability_for_sku(
            sku,
            safety_margin=scope["safety_margin"],
            allowed_positions=scope["allowed_positions"],
        )
    except Exception as e:
        logger.warning("availability_lookup_failed sku=%s: %s", sku, e, exc_info=True)
        return None


def _line_item_is_d1(product: Product, *, listing_ref: str | None = None) -> bool:
    """
    True se o SKU está em D-1 (mesma regra de `_annotate_products` / vitrine).

    Usado ao adicionar linha ao carrinho para alinhar D1DiscountModifier ao preço exibido.
    """
    base_q = _get_price_q(product, listing_ref=listing_ref)
    if not base_q:
        return False
    avail = _get_availability(product.sku)
    badge = _availability_badge(avail, product)
    return bool(avail and badge["css_class"] == "badge-d1")


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
        return {"label": "", "css_class": "badge-available", "can_add_to_cart": True}
    if in_prod > 0:
        return {"label": "Preparando...", "css_class": "badge-preparing", "can_add_to_cart": True}
    if d1 > 0:
        return {"label": "Últimas unidades", "css_class": "badge-d1", "can_add_to_cart": True}
    if avail.get("is_planned"):
        return {"label": "Em breve", "css_class": "badge-planned", "can_add_to_cart": False}
    return {"label": "Indisponível", "css_class": "badge-sold-out", "can_add_to_cart": False}


def _storefront_session_pricing_hints(request: HttpRequest | None) -> tuple[str, int]:
    """Tipo de entrega e subtotal do carrinho (sessão web) — alinha vitrine ao DiscountModifier."""
    if request is None:
        return "", 0
    try:
        from shopman.ordering.models import Channel, Session

        key = request.session.get("cart_session_key")
        if not key:
            return "", 0
        ch = Channel.objects.filter(ref=STOREFRONT_CHANNEL_REF).first()
        if not ch:
            return "", 0
        sess = Session.objects.filter(
            session_key=key,
            channel=ch,
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


def _promo_matches_for_vitrine(promo, sku: str, ctx: dict) -> bool:
    """Igual DiscountModifier._matches, mas se não há fulfillment na sessão e a promo exige tipo,
    testa cada tipo permitido para ainda exibir preço/badge no cardápio."""
    from shopman.modifiers import DiscountModifier

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


def _d1_discount_percent() -> int:
    """Get D-1 discount percent from channel config or default."""
    D1_DISCOUNT_PERCENT = 50

    try:
        from shopman.ordering.models import Channel

        channel = Channel.objects.filter(ref=STOREFRONT_CHANNEL_REF).first()
        if channel and channel.config:
            return channel.config.get("rules", {}).get("d1_discount_percent", D1_DISCOUNT_PERCENT)
    except Exception as e:
        logger.warning("d1_discount_percent_failed: %s", e, exc_info=True)
    return D1_DISCOUNT_PERCENT


def _best_auto_promotion_discount_q(
    sku: str,
    price_q: int,
    sku_collections: list[str],
    *,
    session_total_q: int = 0,
    fulfillment_type: str = "",
):
    """Maior desconto entre promoções automáticas (igual DiscountModifier), para o vitrine.

    Passe ``fulfillment_type`` e ``session_total_q`` da sessão do carrinho (`_storefront_session_pricing_hints`)
    para coincidir com o que o modificador aplica no checkout.
    """
    from shopman.models import Promotion
    from shopman.modifiers import DiscountModifier

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
    """Build template-ready list with price, availability, D-1, promo (mesma regra do carrinho)."""
    if listing_ref is None:
        listing_ref = _get_channel_listing_ref()
    d1_pct = _d1_discount_percent()

    if request is not None and (session_total_q is None or fulfillment_type is None):
        ft_hint, sub_hint = _storefront_session_pricing_hints(request)
        if fulfillment_type is None:
            fulfillment_type = ft_hint
        if session_total_q is None:
            session_total_q = sub_hint
    if session_total_q is None:
        session_total_q = 0
    if fulfillment_type is None:
        fulfillment_type = ""

    from shopman.offering.models import CollectionItem
    from shopman.utils.monetary import monetary_div

    skus = [p.sku for p in products]

    # ── Batch: collections per SKU ────────────────────────────────────────────
    sku_collections: dict[str, list[str]] = {}
    for ci in CollectionItem.objects.filter(product__sku__in=skus).select_related("collection"):
        sku_collections.setdefault(ci.product.sku, []).append(ci.collection.slug)

    # ── Batch: prices — one query for all SKUs ────────────────────────────────
    price_map: dict[str, int] = {}
    if listing_ref:
        for item in (
            ListingItem.objects.filter(
                listing__ref=listing_ref,
                listing__is_active=True,
                product__sku__in=skus,
                is_published=True,
                is_available=True,
            )
            .select_related("product")
            .order_by("-min_qty")
        ):
            # setdefault keeps the first (highest-priority) price per SKU
            # because queryset is ordered by -min_qty (highest tier first)
            price_map.setdefault(item.product.sku, item.price_q)

    # ── Batch: availability — one call for all SKUs ───────────────────────────
    avail_map: dict[str, dict | None] = {}
    if HAS_STOCKING:
        try:
            from shopman.stocking.services.availability import (
                availability_for_skus,
                availability_scope_for_channel,
            )

            scope = availability_scope_for_channel(STOREFRONT_CHANNEL_REF)
            avail_map = availability_for_skus(skus, **scope)
        except Exception as e:
            logger.warning("batch_availability_failed: %s", e, exc_info=True)

    result = []
    for p in products:
        # Price: batch map first, fall back to base_price_q (same as _get_price_q)
        base_q = price_map.get(p.sku) if listing_ref else None
        if base_q is None:
            base_q = p.base_price_q

        avail = avail_map.get(p.sku)
        badge = _availability_badge(avail, p)
        cols = sku_collections.get(p.sku, [])

        d1_price_q = None
        d1_price_display = None
        is_d1 = False
        if avail and badge["css_class"] == "badge-d1" and base_q:
            is_d1 = True
            discount_q = monetary_div(base_q * d1_pct, 100)
            d1_price_q = base_q - discount_q
            d1_price_display = f"R$ {format_money(d1_price_q)}"

        promo_discount_q = 0
        promo_badge = None
        promo_price_display = None
        promo_original_price_display = None
        has_promo_price = False

        if not is_d1 and base_q:
            promo_discount_q, promo = _best_auto_promotion_discount_q(
                p.sku,
                base_q,
                cols,
                session_total_q=session_total_q,
                fulfillment_type=fulfillment_type,
            )
            if promo_discount_q > 0 and promo is not None:
                has_promo_price = True
                eff = base_q - promo_discount_q
                promo_price_display = f"R$ {format_money(eff)}"
                promo_original_price_display = f"R$ {format_money(base_q)}"
                if promo.type == "percent":
                    label = f"-{promo.value}%"
                else:
                    label = f"-R$ {format_money(promo.value)}"
                promo_badge = {
                    "name": promo.name,
                    "type": promo.type,
                    "value": promo.value,
                    "label": label,
                }

        if is_d1 and d1_price_q is not None:
            effective_q = d1_price_q
        elif has_promo_price:
            effective_q = base_q - promo_discount_q
        else:
            effective_q = base_q

        price_display = f"R$ {format_money(effective_q)}" if effective_q else None

        result.append({
            "product": p,
            "price_q": effective_q,
            "price_display": price_display,
            "d1_price_display": d1_price_display,
            "original_price_display": f"R$ {format_money(base_q)}" if is_d1 and base_q else None,
            "is_d1": is_d1,
            "d1_pct": d1_pct,
            "badge": badge,
            "availability": avail,
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
    from shopman.models import Shop

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
    from shopman.models import Shop

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


# Material Symbols Rounded — nomes de ligature por trecho de slug de coleção
COLLECTION_ICONS: dict[str, str] = {
    "paes": "bakery_dining",
    "pao": "bakery_dining",
    "confeitaria": "cake",
    "doces": "icecream",
    "cafes": "local_cafe",
    "cafe": "local_cafe",
    "bebidas": "local_drink",
    "combos": "inventory_2",
    "salgados": "lunch_dining",
    "lanches": "restaurant",
    "especiais": "star",
}


def _collection_icon(slug: str) -> str:
    """Nome do ícone Material Symbols para slug de coleção (default visível no cardápio)."""
    if not slug:
        return "restaurant_menu"
    slug_lower = slug.lower()
    for key, icon in COLLECTION_ICONS.items():
        if key in slug_lower:
            return icon
    return "restaurant_menu"


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
    except Exception as e:
        logger.warning("popular_skus_failed: %s", e, exc_info=True)
        return set()


def _hero_data(listing_ref: str | None = None, request: HttpRequest | None = None) -> dict | None:
    """
    Build hero section data: featured promotion or most popular product.

    Returns dict with keys: product, price_display, promo, image_url, badge
    or None if no suitable hero found.
    """
    try:
        from shopman.models import Promotion

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
                cols: list[str] = []
                try:
                    from shopman.offering.models import CollectionItem

                    cols = list(
                        CollectionItem.objects.filter(product=product).values_list(
                            "collection__slug", flat=True,
                        ),
                    )
                except Exception as e:
                    logger.warning("hero_data_collections_failed: %s", e, exc_info=True)
                    cols = []
                ft_hint, sub_hint = _storefront_session_pricing_hints(request) if request else ("", 0)
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
    except Exception as e:
        logger.warning("hero_data_failed: %s", e, exc_info=True)
    return None


def _min_order_progress(subtotal_q: int, channel_ref: str = STOREFRONT_CHANNEL_REF) -> dict | None:
    """
    Calculate minimum order progress bar data.

    Returns dict with: minimum_q, remaining_q, percent, remaining_display, minimum_display
    or None if no minimum order configured or already met.
    """
    MINIMUM_ORDER_Q = 1000  # R$ 10,00 default
    minimum_q = 0
    try:
        from shopman.ordering.models import Channel

        channel = Channel.objects.filter(ref=channel_ref).first()
        if channel and channel.config:
            validators = (channel.config or {}).get("rules", {}).get("validators", [])
            if "shop.minimum_order" in validators:
                raw = channel.config.get("rules", {}).get("minimum_order_q")
                if raw:
                    minimum_q = int(raw)
                else:
                    from shopman.models import Shop

                    shop = Shop.load()
                    if shop and shop.defaults:
                        raw = shop.defaults.get("rules", {}).get("minimum_order_q")
                        if raw:
                            minimum_q = int(raw)
                    if not minimum_q:
                        minimum_q = MINIMUM_ORDER_Q
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


def _cross_sell_products(
    sku: str,
    listing_ref: str | None = None,
    limit: int = 3,
    request: HttpRequest | None = None,
) -> list[dict]:
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
        return _annotate_products(products, listing_ref=listing_ref, request=request)
    except Exception as e:
        logger.warning("cross_sell_products_failed sku=%s: %s", sku, e, exc_info=True)
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


def _is_happy_hour_active() -> dict:
    """Return happy hour status and config for the storefront channel.

    Returns dict with keys: active (bool), discount_percent (int), end_hour (str).
    """
    from django.conf import settings

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
        return {"active": False, "discount_percent": 0, "start": "16:00", "end": "18:00"}


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


