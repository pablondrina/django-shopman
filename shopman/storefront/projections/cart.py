"""CartProjection — read model for the storefront cart (drawer + page).

Phase 1 / step 3 of the PROJECTION-UI-PLAN. The builder leans on the
existing ``CartService.get_cart`` dict (which already resolves the
Orderman session, availability, discounts and coupon) and re-shapes it
into an immutable frozen dataclass the template consumes without ever
touching mutable dicts or Django model instances.

Higher-order context — minimum order progress and the upsell suggestion
— comes from ``services.storefront_context``.

Never imports from ``shopman.storefront.views.*``. Imports ``CartService``
from ``shopman.storefront.cart`` — a service with no view dependencies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from shopman.offerman.models import Product
from shopman.utils.monetary import format_money

from shopman.storefront.services.storefront_context import (
    minimum_order_progress,
    upsell_suggestion,
)
from shopman.storefront.cart import CartService

from shopman.shop.projections.types import Availability

if TYPE_CHECKING:
    from django.http import HttpRequest  # noqa: F401

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DiscountLineProjection:
    """One aggregated discount row for the cart breakdown.

    ``amount_q`` is the positive cents the customer saved — templates
    prepend the ``-`` sign themselves.
    """

    label: str
    amount_q: int
    amount_display: str


@dataclass(frozen=True)
class CartItemProjection:
    """A single cart line as rendered on the drawer/page."""

    line_id: str
    sku: str
    name: str
    qty: int
    unit_price_q: int
    total_price_q: int
    price_display: str           # unit price, e.g. "R$ 0,90"
    total_display: str           # line total, e.g. "R$ 2,70"
    image_url: str | None

    # Pricing transparency — populated when a promo/coupon reduced the line.
    original_price_display: str | None
    discount_label: str | None

    # Availability snapshot at render-time.
    is_available: bool
    availability_warning: str | None  # short message when qty > stock
    available_qty: int | None         # how many are actually available (None = demand-based, no ceiling)

    # Planned-hold lifecycle state (AVAILABILITY-PLAN §8): the line is
    # either awaiting confirmation of planned production
    # (``is_awaiting_confirmation``) or the planned stock has materialized
    # and the shopper must confirm before the TTL runs out
    # (``is_ready_for_confirmation``). Both are False on a vanilla
    # ready-stock line.
    is_awaiting_confirmation: bool
    is_ready_for_confirmation: bool
    confirmation_deadline_iso: str | None       # ISO 8601 UTC, fuels the Alpine countdown
    confirmation_deadline_display: str | None   # pre-formatted HH:MM for badge copy / toast


@dataclass(frozen=True)
class MinimumOrderProgressProjection:
    """Progress bar data for the ``shop.minimum_order`` rule."""

    minimum_q: int
    remaining_q: int
    percent: int
    minimum_display: str
    remaining_display: str


@dataclass(frozen=True)
class UpsellSuggestionProjection:
    """A single popular item not yet in the cart, offered as upsell."""

    sku: str
    name: str
    price_display: str
    image_url: str | None


@dataclass(frozen=True)
class CartProjection:
    """Full read model for the storefront cart."""

    items: tuple[CartItemProjection, ...]
    items_count: int              # sum of units across lines
    is_empty: bool

    # Totals (dual)
    subtotal_q: int
    subtotal_display: str
    original_subtotal_q: int
    original_subtotal_display: str
    discount_total_q: int
    discount_total_display: str
    has_discount: bool
    discount_lines: tuple[DiscountLineProjection, ...]

    delivery_fee_q: int | None
    delivery_fee_display: str | None
    delivery_is_free: bool
    grand_total_q: int
    grand_total_display: str

    # Coupon
    coupon_code: str | None
    coupon_discount_q: int | None
    coupon_discount_display: str | None

    # Warnings
    has_unavailable_items: bool
    has_awaiting_confirmation_items: bool    # ≥1 line still pre-materialization
    has_ready_for_confirmation_items: bool   # ≥1 line materialized, awaiting shopper confirmation

    # Minimum order + upsell context
    minimum_order_progress: MinimumOrderProgressProjection | None
    upsell: UpsellSuggestionProjection | None


# ──────────────────────────────────────────────────────────────────────
# Builder
# ──────────────────────────────────────────────────────────────────────


def build_cart(
    *,
    request: HttpRequest,
    channel_ref: str,
) -> CartProjection:
    """Build a ``CartProjection`` for the current visitor.

    Always returns a projection — an empty cart becomes
    ``CartProjection(items=(), is_empty=True, ...)``. Never raises for
    business conditions; stock shortfalls surface as per-line warnings.
    """
    raw = CartService.get_cart(request)
    raw_items = raw.get("items") or []

    image_by_sku = _image_by_sku(item["sku"] for item in raw_items if item.get("sku"))

    items = tuple(_build_item(item, image_by_sku) for item in raw_items)
    items_count = sum(int(item.qty) for item in items)
    has_unavailable_items = any(not item.is_available for item in items)
    has_awaiting_confirmation_items = any(item.is_awaiting_confirmation for item in items)
    has_ready_for_confirmation_items = any(item.is_ready_for_confirmation for item in items)

    subtotal_q = int(raw.get("subtotal_q", 0) or 0)
    original_subtotal_q = int(raw.get("original_subtotal_q", subtotal_q) or subtotal_q)
    discount_total_q = int(raw.get("total_discount_q", 0) or 0)
    delivery_fee_q = raw.get("delivery_fee_q")
    grand_total_q = int(raw.get("grand_total_q", subtotal_q) or subtotal_q)

    coupon = raw.get("coupon") or {}
    coupon_code = coupon.get("code")
    coupon_discount_q = (
        int(coupon.get("discount_q") or 0) if coupon else None
    )

    min_order = None
    upsell = None
    if items:
        min_order_raw = minimum_order_progress(original_subtotal_q, channel_ref=channel_ref)
        if min_order_raw:
            min_order = MinimumOrderProgressProjection(
                minimum_q=int(min_order_raw["minimum_q"]),
                remaining_q=int(min_order_raw["remaining_q"]),
                percent=int(min_order_raw["percent"]),
                minimum_display=str(min_order_raw["minimum_display"]),
                remaining_display=str(min_order_raw["remaining_display"]),
            )

        cart_skus = {item.sku for item in items}
        upsell_raw = upsell_suggestion(cart_skus, channel_ref=channel_ref)
        if upsell_raw:
            product = upsell_raw.get("product")
            upsell = UpsellSuggestionProjection(
                sku=str(upsell_raw.get("sku") or ""),
                name=str(getattr(product, "name", "") or ""),
                price_display=str(upsell_raw.get("price_display") or ""),
                image_url=(
                    getattr(product, "image_url", None) or None
                ),
            )

    return CartProjection(
        items=items,
        items_count=items_count,
        is_empty=not items,
        subtotal_q=subtotal_q,
        subtotal_display=_money(subtotal_q),
        original_subtotal_q=original_subtotal_q,
        original_subtotal_display=_money(original_subtotal_q),
        discount_total_q=discount_total_q,
        discount_total_display=_money(discount_total_q),
        has_discount=discount_total_q > 0,
        discount_lines=tuple(
            DiscountLineProjection(
                label=str(row.get("label") or ""),
                amount_q=int(row.get("amount_q") or 0),
                amount_display=str(row.get("amount_display") or _money(row.get("amount_q") or 0)),
            )
            for row in (raw.get("discount_lines") or [])
        ),
        delivery_fee_q=(int(delivery_fee_q) if delivery_fee_q is not None else None),
        delivery_fee_display=raw.get("delivery_fee_display"),
        delivery_is_free=(delivery_fee_q is not None and int(delivery_fee_q) == 0),
        grand_total_q=grand_total_q,
        grand_total_display=_money(grand_total_q),
        coupon_code=coupon_code,
        coupon_discount_q=coupon_discount_q,
        coupon_discount_display=(
            _money(coupon_discount_q) if coupon_discount_q else None
        ),
        has_unavailable_items=has_unavailable_items,
        has_awaiting_confirmation_items=has_awaiting_confirmation_items,
        has_ready_for_confirmation_items=has_ready_for_confirmation_items,
        minimum_order_progress=min_order,
        upsell=upsell,
    )


# ──────────────────────────────────────────────────────────────────────
# Internals
# ──────────────────────────────────────────────────────────────────────


def _build_item(raw: dict, image_by_sku: dict[str, str | None]) -> CartItemProjection:
    sku = str(raw.get("sku") or "")
    qty = int(Decimal(str(raw.get("qty", 0) or 0)))
    unit_price_q = int(raw.get("unit_price_q") or 0)
    total_price_q = int(raw.get("line_total_q") or 0)

    is_unavailable = bool(raw.get("is_unavailable", False))
    available_qty = raw.get("available_qty")
    if available_qty is not None:
        available_qty = int(available_qty)

    # ``is_unavailable`` already reflects the own-hold correction (see
    # CartService.get_cart). When true, the stock really fell behind what
    # this session reserved — surface the exact delta.
    warning: str | None = None
    if is_unavailable:
        if available_qty is not None and available_qty > 0:
            unit_word = "unidade disponível" if available_qty == 1 else "unidades disponíveis"
            warning = f"Apenas {available_qty} {unit_word}"
        else:
            warning = "Indisponível"

    return CartItemProjection(
        line_id=str(raw.get("line_id") or ""),
        sku=sku,
        name=str(raw.get("name") or sku),
        qty=qty,
        unit_price_q=unit_price_q,
        total_price_q=total_price_q,
        price_display=str(raw.get("price_display") or _money(unit_price_q)),
        total_display=str(raw.get("total_display") or _money(total_price_q)),
        image_url=image_by_sku.get(sku),
        original_price_display=raw.get("original_price_display"),
        discount_label=raw.get("discount_label"),
        is_available=not is_unavailable,
        availability_warning=warning,
        available_qty=available_qty,
        is_awaiting_confirmation=bool(raw.get("is_awaiting_confirmation", False)),
        is_ready_for_confirmation=bool(raw.get("is_ready_for_confirmation", False)),
        confirmation_deadline_iso=raw.get("confirmation_deadline_iso"),
        confirmation_deadline_display=raw.get("confirmation_deadline_display"),
    )


def _image_by_sku(skus) -> dict[str, str | None]:
    """Resolve image URLs in a single query for rendering thumbnails."""
    sku_list = [s for s in skus if s]
    if not sku_list:
        return {}
    return {
        p.sku: (p.image_url or None)
        for p in Product.objects.filter(sku__in=sku_list).only("sku", "image_url")
    }


def _money(value_q: int | None) -> str:
    if not value_q:
        return "R$ 0,00"
    return f"R$ {format_money(int(value_q))}"


# Re-export for convenience so ``from shopman.shop.projections import Availability``
# remains the single import the cart template needs alongside ``build_cart``.
__all__ = [
    "Availability",
    "CartItemProjection",
    "CartProjection",
    "DiscountLineProjection",
    "MinimumOrderProgressProjection",
    "UpsellSuggestionProjection",
    "build_cart",
]
