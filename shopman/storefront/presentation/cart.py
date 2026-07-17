"""CartProjection — immutable UI projection for the storefront cart (drawer + page).

Pure presentation: consumes the cart data projection
(``shop.projections.cart.build_cart`` — lines with own-hold-aware
availability, planned-hold state, discount transparency, coupon, totals,
minimum-order progress, upsell and the checkout-eligibility decision) and
shapes it into the frozen dataclass the template renders. Formats ``R$``,
composes "Cupom X"/"Faltam X" copy and the cart actions; resolves nothing
itself.

Never imports from ``shopman.storefront.views.*`` or ``shop.services``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from shopman.utils.monetary import format_money

from shopman.shop.omotenashi import resolve_copy
from shopman.shop.projections import cart as cart_data
from shopman.shop.projections import catalog_context
from shopman.shop.projections.types import Action, Availability

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
    confirmation_deadline_iso: str | None       # ISO 8601 UTC, fuels the countdown na loja Nuxt
    confirmation_deadline_display: str | None   # pre-formatted HH:MM for badge copy / toast
    planned_for_date: str | None                # ISO date da fornada que a linha espera
    planned_for_notice: str | None              # "Previsto para amanhã" (copy omotenashi + data)


@dataclass(frozen=True)
class MinimumOrderProgressProjection:
    """Progress bar data for a minimum-order policy (general or delivery-only)."""

    minimum_q: int
    remaining_q: int
    percent: int
    minimum_display: str
    remaining_display: str
    # Copy do aviso, do registro omotenashi (admin-configurável). O Vue monta
    # "{warning_prefix} {remaining_display} {warning_middle} {minimum_display}"
    # + o CTA acionável.
    warning_prefix: str = ""
    warning_middle: str = ""
    add_more_cta: str = ""


@dataclass(frozen=True)
class FreeDeliveryProgressProjection:
    """Progress bar data for the free-delivery upsell."""

    threshold_q: int
    remaining_q: int
    percent: int
    threshold_display: str
    remaining_display: str


@dataclass(frozen=True)
class UpsellSuggestionProjection:
    """A single popular item not yet in the cart, offered as upsell."""

    sku: str
    name: str
    unit_price_q: int
    price_display: str
    image_url: str | None


@dataclass(frozen=True)
class CartProjection:
    """Full projection for the storefront cart."""

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
    delivery_zone_error: bool
    # Distância loja→endereço, p/ justificar a taxa no checkout ("a 2 km · R$ 5,00").
    delivery_distance_km: float | None
    delivery_distance_display: str | None
    grand_total_q: int
    grand_total_display: str
    loyalty_applied: bool

    # Coupon
    coupon_code: str | None
    coupon_discount_q: int | None
    coupon_discount_display: str | None

    # Warnings
    has_unavailable_items: bool
    has_awaiting_confirmation_items: bool    # ≥1 line still pre-materialization
    has_ready_for_confirmation_items: bool   # ≥1 line materialized, awaiting shopper confirmation
    # Copy do banner de estoque alterado (registro omotenashi, admin-configurável);
    # o Vue mostra quando ``has_unavailable_items`` — acima do tratamento por-item.
    unavailable_banner: str
    # Aviso sob o badge "Aguardando confirmação" por item (registro omotenashi,
    # admin-configurável); o Vue mostra na linha em espera de materialização.
    awaiting_confirmation_notice: str

    # Minimum order + upsell context
    minimum_order_progress: MinimumOrderProgressProjection | None
    # Delivery-only minimum, shown in the delivery step ("Pedido mínimo para
    # entrega R$X · faltam R$Y"). Pickup never carries one.
    delivery_minimum_progress: MinimumOrderProgressProjection | None
    # Free-delivery upsell ("faltam R$Y para frete grátis"), reuses the bar.
    free_delivery_progress: FreeDeliveryProgressProjection | None
    upsell: UpsellSuggestionProjection | None

    # Canonical cart-level actions. Surfaces render these instead of deriving
    # checkout eligibility from local cart flags.
    actions: tuple[Action, ...]


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
    session_key = request.session.get("cart_session_key")
    data = cart_data.build_cart(session_key, channel_ref)

    image_by_sku = _image_by_sku(line.sku for line in data.lines)
    planned_notice_template = (
        resolve_copy("CART_WAITLIST_PLANNED_DATE", moment="*", audience="*").message or ""
    ).strip()
    items = tuple(
        _present_line(line, image_by_sku, planned_notice_template) for line in data.lines
    )

    min_order = present_minimum_order(data.minimum_order)
    delivery_minimum = present_minimum_order(data.delivery_minimum)
    free_delivery = present_free_delivery(data.free_delivery)
    upsell = present_upsell(data.upsell)
    actions = _cart_actions(data, min_order)

    return CartProjection(
        items=items,
        items_count=data.count,
        is_empty=data.is_empty,
        subtotal_q=data.subtotal_q,
        subtotal_display=_money(data.subtotal_q),
        original_subtotal_q=data.original_subtotal_q,
        original_subtotal_display=_money(data.original_subtotal_q),
        discount_total_q=data.discount_total_q,
        discount_total_display=_money(data.discount_total_q),
        has_discount=data.discount_total_q > 0,
        discount_lines=tuple(_present_discount_line(dl) for dl in data.discount_lines),
        delivery_fee_q=data.delivery_fee_q,
        delivery_fee_display=_delivery_fee_display(data),
        delivery_is_free=data.delivery_is_free,
        delivery_zone_error=data.delivery_zone_error,
        delivery_distance_km=data.delivery_distance_km,
        delivery_distance_display=_delivery_distance_display(data),
        loyalty_applied=data.loyalty_applied,
        grand_total_q=data.grand_total_q,
        grand_total_display=_money(data.grand_total_q),
        coupon_code=data.coupon.code if data.coupon else None,
        coupon_discount_q=data.coupon.discount_q if data.coupon else None,
        coupon_discount_display=(
            _money(data.coupon.discount_q)
            if data.coupon and data.coupon.discount_q
            else None
        ),
        has_unavailable_items=data.has_unavailable,
        has_awaiting_confirmation_items=data.has_awaiting_confirmation,
        has_ready_for_confirmation_items=data.has_ready_for_confirmation,
        unavailable_banner=(
            resolve_copy("CART_UNAVAILABLE_BANNER", moment="*", audience="*").message or ""
        ).strip(),
        awaiting_confirmation_notice=(
            resolve_copy("CART_WAITLIST_NOTICE", moment="*", audience="*").message or ""
        ).strip(),
        minimum_order_progress=min_order,
        delivery_minimum_progress=delivery_minimum,
        free_delivery_progress=free_delivery,
        upsell=upsell,
        actions=actions,
    )


# ──────────────────────────────────────────────────────────────────────
# Internals
# ──────────────────────────────────────────────────────────────────────


def _present_line(
    line: cart_data.CartLineProjection,
    image_by_sku: dict[str, str | None],
    planned_notice_template: str = "",
) -> CartItemProjection:
    # ``is_available`` already reflects the own-hold correction. When false,
    # the stock really fell behind what this session reserved — surface the
    # exact delta.
    warning: str | None = None
    if not line.is_available:
        if line.available_qty is not None and line.available_qty > 0:
            unit_word = "unidade disponível" if line.available_qty == 1 else "unidades disponíveis"
            warning = f"Apenas {line.available_qty} {unit_word}"
        else:
            warning = "Indisponível"

    discount_label: str | None = None
    if line.discount_name:
        discount_label = (
            f"Cupom {line.discount_name}" if line.discount_is_coupon else line.discount_name
        )

    return CartItemProjection(
        line_id=line.line_id,
        sku=line.sku,
        name=line.name,
        qty=line.qty,
        unit_price_q=line.unit_price_q,
        total_price_q=line.line_total_q,
        price_display=_money(line.unit_price_q),
        total_display=_money(line.line_total_q),
        image_url=image_by_sku.get(line.sku),
        original_price_display=(
            _money(line.original_price_q) if line.original_price_q is not None else None
        ),
        discount_label=discount_label,
        is_available=line.is_available,
        availability_warning=warning,
        available_qty=line.available_qty,
        is_awaiting_confirmation=line.is_awaiting_confirmation,
        is_ready_for_confirmation=line.is_ready_for_confirmation,
        confirmation_deadline_iso=line.confirmation_deadline_iso,
        confirmation_deadline_display=_deadline_display(line.confirmation_deadline_iso),
        planned_for_date=line.planned_for_date,
        planned_for_notice=_planned_for_notice(line, planned_notice_template),
    )


def _present_discount_line(dl: cart_data.CartDiscountLineProjection) -> DiscountLineProjection:
    return DiscountLineProjection(
        label=f"Cupom {dl.name}" if dl.is_coupon else dl.name,
        amount_q=dl.amount_q,
        amount_display=_money(dl.amount_q),
    )


def _delivery_fee_display(data: cart_data.CartProjection) -> str | None:
    if data.delivery_fee_q is None:
        return None
    return "Grátis" if data.delivery_is_free else _money(data.delivery_fee_q)


def _delivery_distance_display(data: cart_data.CartProjection) -> str | None:
    km = data.delivery_distance_km
    if km is None:
        return None
    if km == int(km):
        return f"{int(km)} km"
    return f"{km:.1f}".replace(".", ",") + " km"


def _planned_for_notice(
    line: cart_data.CartLineProjection, template: str,
) -> str | None:
    """Compose the waitlist line's expected-batch notice ("Previsto para amanhã").

    Only meaningful while the line still awaits materialization — a ready
    line already shows the confirmation deadline instead.
    """
    if not line.is_awaiting_confirmation or not template:
        return None
    display = _planned_for_display(line.planned_for_date)
    if not display:
        return None
    return template.replace("{date}", display)


def _planned_for_display(planned_iso: str | None) -> str | None:
    # A data já chega TRUTHFUL do read-side (``shop.projections.cart`` fixa o piso
    # fulfillável: nunca "hoje" com a loja fechada). Aqui é só formatação.
    if not planned_iso:
        return None
    try:
        from datetime import date, timedelta

        from django.utils import formats
        from django.utils import timezone as _tz

        planned = date.fromisoformat(planned_iso)
        today = _tz.localdate()
        if planned <= today:
            return "hoje"
        if planned == today + timedelta(days=1):
            return "amanhã"
        return f"{formats.date_format(planned, 'l')}, {formats.date_format(planned, 'd/m')}"
    except Exception:
        logger.debug("cart._planned_for_display degraded", exc_info=True)
        return None


def _deadline_display(deadline_iso: str | None) -> str | None:
    if not deadline_iso:
        return None
    try:
        from datetime import datetime

        from django.utils import timezone as _tz

        return _tz.localtime(datetime.fromisoformat(deadline_iso)).strftime("%H:%M")
    except Exception:
        logger.debug("cart._deadline_display degraded", exc_info=True)
        return None


def present_minimum_order(
    data: cart_data.MinimumOrderProgressProjection | None,
) -> MinimumOrderProgressProjection | None:
    """Format the minimum-order progress data into the cart presentation DTO.

    Shared by the cart and the checkout order-summary partial so the ``R$``
    strings come from one place.
    """
    if data is None:
        return None

    def _msg(key: str) -> str:
        return (resolve_copy(key, moment="*", audience="*").message or "").strip()

    return MinimumOrderProgressProjection(
        minimum_q=data.minimum_q,
        remaining_q=data.remaining_q,
        percent=data.percent,
        minimum_display=_money(data.minimum_q),
        remaining_display=_money(data.remaining_q),
        warning_prefix=_msg("MIN_ORDER_WARNING_PREFIX"),
        warning_middle=_msg("MIN_ORDER_WARNING_MIDDLE"),
        add_more_cta=_msg("MIN_ORDER_WARNING"),
    )


def present_free_delivery(
    data: cart_data.FreeDeliveryProgressProjection | None,
) -> FreeDeliveryProgressProjection | None:
    """Format the free-delivery progress data into the cart presentation DTO."""
    if data is None:
        return None
    return FreeDeliveryProgressProjection(
        threshold_q=data.threshold_q,
        remaining_q=data.remaining_q,
        percent=data.percent,
        threshold_display=_money(data.threshold_q),
        remaining_display=_money(data.remaining_q),
    )


def present_upsell(
    data: cart_data.UpsellSuggestionProjection | None,
) -> UpsellSuggestionProjection | None:
    """Format the upsell suggestion data into the cart presentation DTO."""
    if data is None:
        return None
    return UpsellSuggestionProjection(
        sku=data.sku,
        name=data.name,
        unit_price_q=data.unit_price_q,
        price_display=_money(data.unit_price_q) if data.unit_price_q else "",
        image_url=data.image_url,
    )


def _image_by_sku(skus) -> dict[str, str | None]:
    """Resolve image URLs in a single query for rendering thumbnails."""
    return catalog_context.image_urls_by_sku(skus)


def _money(value_q: int | None) -> str:
    if not value_q:
        return "R$ 0,00"
    return f"R$ {format_money(int(value_q))}"


def _cart_actions(
    data: cart_data.CartProjection,
    minimum_order_progress: MinimumOrderProgressProjection | None,
) -> tuple[Action, ...]:
    """Map the data projection's checkout-eligibility decision to actions.

    The orchestrator decided ``can_checkout`` + ``checkout_block_reason``; the
    presentation only renders the matching label/reason copy.
    """
    checkout_enabled = data.can_checkout
    checkout_reason = ""
    checkout_label = "Finalizar pedido"

    def _reason(key: str, fallback: str) -> str:
        return resolve_copy(key, moment="*", audience="*").message or fallback

    if data.checkout_block_reason == "empty":
        checkout_reason = _reason("CART_CHECKOUT_BLOCK_EMPTY", "Sacola vazia.")
    elif data.checkout_block_reason == "unavailable":
        checkout_reason = _reason(
            "CART_CHECKOUT_BLOCK_UNAVAILABLE", "Revise itens indisponíveis antes de finalizar."
        )
    elif data.checkout_block_reason == "below_minimum":
        checkout_reason = (
            f"Faltam {minimum_order_progress.remaining_display} para o pedido mínimo."
            if minimum_order_progress is not None
            else _reason("CART_CHECKOUT_BLOCK_MIN_ORDER", "Pedido mínimo não atingido.")
        )
    elif data.has_ready_for_confirmation:
        checkout_label = "Confirmar agora"

    return (
        Action(
            ref="checkout",
            kind="link",
            label=checkout_label,
            priority="primary",
            enabled=checkout_enabled,
            reason=checkout_reason,
            href="/checkout",
        ),
        Action(
            ref="continue_shopping",
            kind="link",
            label="Continuar comprando",
            priority="secondary",
            enabled=True,
            href="/menu",
        ),
    )


# Re-export for convenience so ``from shopman.shop.projections import Availability``
# remains the single import the cart template needs alongside ``build_cart``.
__all__ = [
    "Availability",
    "CartItemProjection",
    "CartProjection",
    "DiscountLineProjection",
    "FreeDeliveryProgressProjection",
    "MinimumOrderProgressProjection",
    "UpsellSuggestionProjection",
    "build_cart",
]
