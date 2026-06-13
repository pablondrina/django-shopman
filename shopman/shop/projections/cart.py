"""Cart read-side projection — semantic data, surface-agnostic.

The orchestrator resolves the cart once, for any surface: lines (with
own-hold-aware availability and planned-hold state), discount transparency,
coupon, delivery fee, totals, minimum-order progress, upsell and the
checkout-eligibility decision (``can_checkout`` + ``checkout_block_reason``).
Everything is semantic — cents (``_q``), enums, ISO timestamps, booleans,
refs. Presentation (``R$`` formatting, "Cupom X"/"Faltam X" copy, the
``Action`` labels) lives in ``<surface>/presentation/``.

This is the single source of cart-data resolution: ``CartService.get_cart``
(the legacy dict) and ``storefront/presentation/cart`` both build from
``build_cart`` — no surface re-derives availability, discount or totals.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)

DEFAULT_STOREFRONT_CHANNEL_REF = "web"
_MINIMUM_ORDER_Q_DEFAULT = 1000  # R$ 10,00 fallback when the rule is active

# Pricing-modifier discount keys aggregated into the cart breakdown.
_PRICING_MODIFIER_KEYS = (
    "d1_discount",
    "employee_discount",
    "happy_hour",
    "loyalty_redeem",
    "manual_discount",
)


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


@dataclass(frozen=True)
class CartLineProjection:
    """A single cart line — semantic, own-hold-aware availability included."""

    line_id: str
    sku: str
    name: str
    qty: int
    unit_price_q: int
    line_total_q: int

    # Availability at render-time (own-hold corrected: a session holding all
    # of its own stock is NOT flagged unavailable).
    is_available: bool
    available_qty: int | None  # None = demand-based / no ceiling

    # Planned-hold lifecycle (AVAILABILITY-PLAN §8).
    is_awaiting_confirmation: bool
    is_ready_for_confirmation: bool
    confirmation_deadline_iso: str | None

    # Pricing transparency — set when a promo/coupon reduced the line.
    original_price_q: int | None
    discount_name: str | None  # raw promo/coupon name (presentation prefixes "Cupom")
    discount_is_coupon: bool


@dataclass(frozen=True)
class CartDiscountLineProjection:
    """One aggregated discount row — positive cents saved, one per origin."""

    name: str
    is_coupon: bool
    amount_q: int


@dataclass(frozen=True)
class CartCouponProjection:
    """Applied coupon — code + cents saved."""

    code: str
    discount_q: int


@dataclass(frozen=True)
class CartProjection:
    """Full cart data projection — surface-agnostic, policy-laden."""

    session_key: str
    lines: tuple[CartLineProjection, ...]
    count: int
    is_empty: bool

    subtotal_q: int
    original_subtotal_q: int
    discount_total_q: int
    discount_lines: tuple[CartDiscountLineProjection, ...]
    coupon: CartCouponProjection | None

    delivery_fee_q: int | None
    delivery_is_free: bool
    delivery_zone_error: bool
    grand_total_q: int

    loyalty_applied: bool

    has_unavailable: bool
    has_awaiting_confirmation: bool
    has_ready_for_confirmation: bool

    minimum_order: MinimumOrderProgressProjection | None
    upsell: UpsellSuggestionProjection | None

    can_checkout: bool
    checkout_block_reason: str  # "" | "empty" | "unavailable" | "below_minimum"


def _empty_cart(session_key: str = "") -> CartProjection:
    return CartProjection(
        session_key=session_key,
        lines=(),
        count=0,
        is_empty=True,
        subtotal_q=0,
        original_subtotal_q=0,
        discount_total_q=0,
        discount_lines=(),
        coupon=None,
        delivery_fee_q=None,
        delivery_is_free=False,
        delivery_zone_error=False,
        grand_total_q=0,
        loyalty_applied=False,
        has_unavailable=False,
        has_awaiting_confirmation=False,
        has_ready_for_confirmation=False,
        minimum_order=None,
        upsell=None,
        can_checkout=False,
        checkout_block_reason="empty",
    )


def build_cart(
    session_key: str | None,
    channel_ref: str = DEFAULT_STOREFRONT_CHANNEL_REF,
) -> CartProjection:
    """Resolve the full cart data for ``session_key`` on ``channel_ref``.

    Always returns a projection — an empty/expired cart becomes the empty
    projection. Never raises for business conditions; stock shortfalls surface
    as per-line ``is_available`` flags.
    """
    if not session_key:
        return _empty_cart()

    from shopman.orderman.models import Session

    session = Session.objects.filter(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
    ).first()
    if session is None:
        return _empty_cart()

    raw_items = [dict(item) for item in (session.items or [])]
    if not raw_items:
        return _empty_cart(session_key)

    skus = [item.get("sku", "") for item in raw_items]
    names_by_sku = _names_by_sku(skus)
    avail_map, own_holds = _availability(skus, session_key, channel_ref)

    pricing = session.pricing or {}
    discount_data = pricing.get("discount", {})
    discount_items = {d["sku"]: d for d in discount_data.get("items", [])}

    lines = tuple(
        _build_line(item, names_by_sku, avail_map, own_holds, discount_items, session_key)
        for item in raw_items
    )

    count = sum(line.qty for line in lines)
    subtotal_q = sum(line.line_total_q for line in lines)
    has_unavailable = any(not line.is_available for line in lines)
    has_awaiting = any(line.is_awaiting_confirmation for line in lines)
    has_ready = any(line.is_ready_for_confirmation for line in lines)

    discount_total_q = int(discount_data.get("total_discount_q", 0) or 0)
    discount_total_q += sum(
        int((pricing.get(key) or {}).get("total_discount_q", 0))
        for key in _PRICING_MODIFIER_KEYS
    )
    original_subtotal_q = subtotal_q + discount_total_q
    discount_lines = _discount_lines(discount_data, pricing)
    coupon = _coupon(session.data or {}, pricing)

    delivery_fee_q = (session.data or {}).get("delivery_fee_q")
    delivery_fee_q = int(delivery_fee_q) if delivery_fee_q is not None else None
    delivery_zone_error = bool((session.data or {}).get("delivery_zone_error"))
    grand_total_q = subtotal_q + (delivery_fee_q or 0)

    minimum_order = build_minimum_order_progress(original_subtotal_q, channel_ref)
    upsell = build_upsell_suggestion({line.sku for line in lines}, channel_ref=channel_ref)

    can_checkout, block_reason = _checkout_eligibility(
        is_empty=False,
        has_unavailable=has_unavailable,
        minimum_order=minimum_order,
    )

    return CartProjection(
        session_key=session_key,
        lines=lines,
        count=count,
        is_empty=False,
        subtotal_q=subtotal_q,
        original_subtotal_q=original_subtotal_q,
        discount_total_q=discount_total_q,
        discount_lines=discount_lines,
        coupon=coupon,
        delivery_fee_q=delivery_fee_q,
        delivery_is_free=(delivery_fee_q is not None and delivery_fee_q == 0),
        delivery_zone_error=delivery_zone_error,
        grand_total_q=grand_total_q,
        loyalty_applied="loyalty_redeem" in pricing,
        has_unavailable=has_unavailable,
        has_awaiting_confirmation=has_awaiting,
        has_ready_for_confirmation=has_ready,
        minimum_order=minimum_order,
        upsell=upsell,
        can_checkout=can_checkout,
        checkout_block_reason=block_reason,
    )


# ──────────────────────────────────────────────────────────────────────
# Internals — line + availability resolution (ported from CartService.get_cart)
# ──────────────────────────────────────────────────────────────────────


def _names_by_sku(skus: list[str]) -> dict[str, str]:
    from shopman.offerman.models import Product

    return {
        p.sku: p.name
        for p in Product.objects.filter(sku__in=skus).only("sku", "name")
    }


def _availability(
    skus: list[str], session_key: str, channel_ref: str,
) -> tuple[dict[str, dict | None], dict[str, Decimal]]:
    """Batch availability + own-hold lookup; degrades to empty maps on failure
    (including when Stockman is not installed — the import simply raises)."""
    try:
        from shopman.stockman.services.availability import availability_for_skus

        from shopman.shop.adapters import stock as stock_adapter
        from shopman.shop.services import availability as availability_service

        scope = stock_adapter.get_channel_scope(channel_ref)
        avail_map = availability_for_skus(
            skus,
            safety_margin=scope["safety_margin"],
            allowed_positions=scope["allowed_positions"],
            excluded_positions=scope.get("excluded_positions"),
        )
        own_holds = availability_service.own_holds_by_sku(session_key, skus)
        return avail_map, own_holds
    except Exception:
        logger.warning("cart.availability check failed skus=%s", skus, exc_info=True)
        return {}, {}


def _build_line(
    item: dict,
    names_by_sku: dict[str, str],
    avail_map: dict[str, dict | None],
    own_holds: dict[str, Decimal],
    discount_items: dict[str, dict],
    session_key: str,
) -> CartLineProjection:
    sku = item.get("sku", "")
    qty = int(Decimal(str(item.get("qty", 0) or 0)))
    name = item.get("name") or names_by_sku.get(sku) or sku

    is_awaiting, is_ready, deadline_iso = _planned_hold(session_key, sku)
    is_available, available_qty = _line_availability(
        sku, qty, avail_map.get(sku), own_holds,
    )

    disc = discount_items.get(sku)
    original_price_q = int(disc["original_price_q"]) if disc else None
    discount_name = (disc.get("name") or "") if disc else None
    discount_is_coupon = bool(disc and disc.get("type") == "coupon")

    return CartLineProjection(
        line_id=str(item.get("line_id") or ""),
        sku=sku,
        name=name,
        qty=qty,
        unit_price_q=int(item.get("unit_price_q", 0) or 0),
        line_total_q=int(item.get("line_total_q", 0) or 0),
        is_available=is_available,
        available_qty=available_qty,
        is_awaiting_confirmation=is_awaiting,
        is_ready_for_confirmation=is_ready,
        confirmation_deadline_iso=deadline_iso,
        original_price_q=original_price_q,
        discount_name=discount_name or None,
        discount_is_coupon=discount_is_coupon,
    )


def _planned_hold(session_key: str, sku: str) -> tuple[bool, bool, str | None]:
    from shopman.shop.services import availability as availability_service

    planned = availability_service.classify_planned_hold_for_session_sku(session_key, sku)
    deadline = planned.get("deadline")
    return (
        planned["is_awaiting_confirmation"],
        planned["is_ready_for_confirmation"],
        deadline.isoformat() if deadline is not None else None,
    )


def _line_availability(
    sku: str, qty: int, avail: dict | None, own_holds: dict[str, Decimal],
) -> tuple[bool, int | None]:
    """Own-hold-corrected availability: a line is unavailable only when the
    shortage is real (external), not when the session's own hold drained
    ``total_promisable``. Returns ``(is_available, available_qty)``.
    """
    if avail is None:
        return True, None
    if avail.get("availability_policy") == "demand_ok" and not avail.get("is_paused", False):
        return True, None

    own_hold = int(own_holds.get(sku, Decimal("0")))
    ready_physical = int(avail.get("ready_physical", 0) or 0)
    held_ready = int(avail.get("held_ready", 0) or 0)
    margin = int(avail.get("safety_margin", 0) or 0)
    other_holds = max(0, held_ready - own_hold)
    max_orderable = max(0, ready_physical - other_holds - margin)
    return max_orderable >= qty, max_orderable


def _discount_lines(discount_data: dict, pricing: dict) -> tuple[CartDiscountLineProjection, ...]:
    """One row per discount origin, aggregated. Coupon/promo carry the raw
    name + ``is_coupon``; the presentation composes the label.
    """
    agg: dict[tuple[bool, str], int] = defaultdict(int)
    for d in discount_data.get("items") or []:
        amt = int(d.get("discount_q", 0)) * int(d.get("qty", 0))
        if amt <= 0:
            continue
        name = (d.get("name") or "").strip() or "Promoção"
        agg[(d.get("type") == "coupon", name)] += amt
    for key in _PRICING_MODIFIER_KEYS:
        mod_data = pricing.get(key) or {}
        amt = int(mod_data.get("total_discount_q", 0))
        if amt > 0:
            agg[(False, mod_data.get("label", key))] += amt
    return tuple(
        CartDiscountLineProjection(name=name, is_coupon=is_coupon, amount_q=amt)
        for (is_coupon, name), amt in sorted(agg.items(), key=lambda kv: -kv[1])
    )


def _coupon(data: dict, pricing: dict) -> CartCouponProjection | None:
    code = data.get("coupon_code")
    coupon_data = pricing.get("coupon")
    if not (code and coupon_data):
        return None
    return CartCouponProjection(code=code, discount_q=int(coupon_data.get("discount_q", 0) or 0))


def _checkout_eligibility(
    *,
    is_empty: bool,
    has_unavailable: bool,
    minimum_order: MinimumOrderProgressProjection | None,
) -> tuple[bool, str]:
    if is_empty:
        return False, "empty"
    if has_unavailable:
        return False, "unavailable"
    if minimum_order is not None:
        return False, "below_minimum"
    return True, ""


# ──────────────────────────────────────────────────────────────────────
# Minimum-order + upsell (consumed by build_cart and the live mutation payload)
# ──────────────────────────────────────────────────────────────────────


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
    "CartCouponProjection",
    "CartDiscountLineProjection",
    "CartLineProjection",
    "CartProjection",
    "MinimumOrderProgressProjection",
    "UpsellSuggestionProjection",
    "build_cart",
    "build_minimum_order_progress",
    "build_upsell_suggestion",
]
