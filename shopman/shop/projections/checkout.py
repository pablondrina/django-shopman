"""CheckoutProjection — read model for the checkout page (Fase 2).

The builder pulls together all static context the checkout form needs:
cart summary (via CartProjection), customer pre-fills, saved addresses,
payment methods, pickup slots, and shop config. It does NOT carry transient
form state (errors, POST values) — those travel separately in the view
context so the projection remains a stable read model.

Never imports from ``shopman.shop.web.views.*``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from shopman.utils.monetary import format_money

from .cart import CartProjection, build_cart
from .types import (
    PAYMENT_METHOD_LABELS_PT,
    PaymentMethodOptionProjection,
    PickupSlotProjection,
    SavedAddressProjection,
)

if TYPE_CHECKING:
    from django.http import HttpRequest

logger = logging.getLogger(__name__)

_DEFAULT_CHANNEL_REF = "web"


# ──────────────────────────────────────────────────────────────────────
# Dataclass
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CheckoutProjection:
    """Full read model for the checkout page.

    Templates consume this alongside a separate ``errors`` dict and
    ``form_data`` dict supplied by the view for error re-renders.
    """

    # Cart summary panel
    cart: CartProjection

    # Customer pre-fills
    customer_phone: str
    customer_name: str
    is_authenticated: bool

    # Saved addresses
    saved_addresses: tuple[SavedAddressProjection, ...]

    # Payment methods available on this channel
    payment_methods: tuple[PaymentMethodOptionProjection, ...]
    default_payment_method: str

    # Fulfillment availability
    has_pickup: bool
    has_delivery: bool

    # Pickup slots
    pickup_slots: tuple[PickupSlotProjection, ...]
    earliest_slot_ref: str | None

    # Loyalty
    loyalty_balance_q: int
    loyalty_value_display: str | None

    # Shop configuration (pre-serialised for Alpine)
    max_preorder_days: int
    closed_dates_json: str

    # Dev toggle
    is_debug: bool


# ──────────────────────────────────────────────────────────────────────
# Builder
# ──────────────────────────────────────────────────────────────────────


def build_checkout(
    *,
    request: HttpRequest,
    channel_ref: str = _DEFAULT_CHANNEL_REF,
) -> CheckoutProjection:
    """Build a ``CheckoutProjection`` for the current visitor.

    Always returns a projection. Missing services (loyalty down, addresses
    unavailable) degrade gracefully to empty/zero values.
    """
    from django.conf import settings

    cart = build_cart(request=request, channel_ref=channel_ref)

    customer_info = getattr(request, "customer", None)
    customer_phone = ""
    customer_name = ""
    saved_addresses: tuple[SavedAddressProjection, ...] = ()
    loyalty_balance_q = 0
    loyalty_value_display: str | None = None

    if customer_info:
        customer_phone = customer_info.phone or ""
        customer_name = customer_info.name or ""
        saved_addresses, loyalty_balance_q, loyalty_value_display = _load_customer_context(
            customer_info,
        )

    payment_methods = _payment_methods(channel_ref)
    pickup_slots, earliest_slot_ref = _pickup_slots(cart)
    max_preorder_days, closed_dates = _shop_config()

    return CheckoutProjection(
        cart=cart,
        customer_phone=customer_phone,
        customer_name=customer_name,
        is_authenticated=customer_info is not None,
        saved_addresses=saved_addresses,
        payment_methods=payment_methods,
        default_payment_method=payment_methods[0].ref if payment_methods else "cash",
        has_pickup=True,
        has_delivery=True,
        pickup_slots=pickup_slots,
        earliest_slot_ref=earliest_slot_ref,
        loyalty_balance_q=loyalty_balance_q,
        loyalty_value_display=loyalty_value_display,
        max_preorder_days=max_preorder_days,
        closed_dates_json=json.dumps(closed_dates),
        is_debug=settings.DEBUG,
    )


# ──────────────────────────────────────────────────────────────────────
# Internals
# ──────────────────────────────────────────────────────────────────────


def _load_customer_context(
    customer_info,
) -> tuple[tuple[SavedAddressProjection, ...], int, str | None]:
    """Return (saved_addresses, loyalty_balance_q, loyalty_value_display)."""
    saved_addresses: tuple[SavedAddressProjection, ...] = ()
    loyalty_balance_q = 0
    loyalty_value_display: str | None = None

    try:
        from shopman.guestman.services import address as address_service
        from shopman.guestman.services import customer as customer_service

        customer_obj = customer_service.get_by_uuid(customer_info.uuid)
        if customer_obj:
            saved_addresses = tuple(
                SavedAddressProjection(
                    id=addr.id,
                    formatted_address=addr.formatted_address or "",
                    complement=addr.complement or "",
                    label=addr.display_label or addr.formatted_address or "",
                    is_default=addr.is_default,
                )
                for addr in address_service.addresses(customer_obj.ref)
            )

            try:
                from shopman.guestman.contrib.loyalty import LoyaltyService

                loyalty_balance_q = LoyaltyService.get_balance(customer_obj.ref)
                if loyalty_balance_q > 0:
                    loyalty_value_display = f"R$ {format_money(loyalty_balance_q)}"
            except Exception:
                logger.exception("checkout_projection_loyalty_failed")
    except Exception:
        logger.exception("checkout_projection_customer_context_failed")

    return saved_addresses, loyalty_balance_q, loyalty_value_display


def _payment_methods(channel_ref: str) -> tuple[PaymentMethodOptionProjection, ...]:
    """Resolve channel payment methods from ChannelConfig."""
    try:
        from shopman.shop.config import ChannelConfig
        from shopman.shop.models import Channel

        channel = Channel.objects.get(ref=channel_ref)
        methods = ChannelConfig.for_channel(channel).payment.available_methods
    except Exception:
        methods = ["cash"]

    return tuple(
        PaymentMethodOptionProjection(
            ref=m,
            label=PAYMENT_METHOD_LABELS_PT.get(m, m),
            is_default=(i == 0),
        )
        for i, m in enumerate(methods)
    )


def _pickup_slots(
    cart: CartProjection,
) -> tuple[tuple[PickupSlotProjection, ...], str | None]:
    """Resolve pickup slots and earliest available slot for the cart."""
    try:
        from shopman.shop.services.pickup_slots import annotate_slots_for_checkout

        cart_skus = [item.sku for item in cart.items]
        ctx = annotate_slots_for_checkout(cart_skus)
        raw_slots = ctx.get("pickup_slots") or []
        slots = tuple(
            PickupSlotProjection(
                ref=str(s.get("ref") or ""),
                label=str(s.get("label") or ""),
                starts_at=str(s.get("starts_at") or ""),
            )
            for s in raw_slots
        )
        earliest = ctx.get("earliest_slot_ref")
        return slots, earliest
    except Exception:
        logger.exception("checkout_projection_slots_failed")
        return (), None


def _shop_config() -> tuple[int, list]:
    """Return (max_preorder_days, closed_dates)."""
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        if shop:
            defaults = shop.defaults or {}
            return int(defaults.get("max_preorder_days", 30)), defaults.get("closed_dates", [])
    except Exception:
        logger.exception("checkout_projection_shop_config_failed")
    return 30, []


__all__ = ["CheckoutProjection", "build_checkout"]
