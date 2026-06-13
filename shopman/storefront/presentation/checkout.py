"""CheckoutProjection — immutable UI projection for the checkout page (Fase 2).

The builder pulls together all static context the checkout form needs:
cart summary (via CartProjection), customer pre-fills, saved addresses,
payment methods, pickup slots, and shop config. It does NOT carry transient
form state (errors, POST values) — those travel separately in the view
context so the projection remains a stable contract.

Never imports from ``shopman.storefront.views.*``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from shopman.utils.monetary import format_money

from shopman.shop.projections import customer_context
from shopman.shop.projections.channel_policy import ChannelPolicyResolution, resolve_channel_policy
from shopman.shop.projections.copy import build_copy
from shopman.shop.projections.interaction_context import InteractionContext
from shopman.shop.projections.types import (
    Action,
    PickupSlotProjection,
    SavedAddressProjection,
)
from shopman.storefront.presentation.status import payment_method_label
from shopman.storefront.presentation.types import PaymentMethodOptionProjection

from .cart import CartProjection, build_cart

if TYPE_CHECKING:
    from django.http import HttpRequest

logger = logging.getLogger(__name__)

_DEFAULT_CHANNEL_REF = "web"


# ──────────────────────────────────────────────────────────────────────
# Dataclass
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CheckoutProjection:
    """Full projection for the checkout page.

    Templates consume this alongside a separate ``errors`` dict and
    ``form_data`` dict supplied by the view for error re-renders.
    """

    # Cart summary panel
    cart: CartProjection

    # Customer pre-fills
    customer_phone: str
    customer_name: str
    is_authenticated: bool
    requires_authentication: bool
    auth_action: Action | None

    # Saved addresses
    saved_addresses: tuple[SavedAddressProjection, ...]
    # Id of the address to pre-select (default → geo → last → most-used → None)
    preselected_address_id: int | None

    # Payment methods available on this channel
    payment_methods: tuple[PaymentMethodOptionProjection, ...]
    default_payment_method: str

    # Resolved options/actions for the surface
    actions: tuple[Action, ...]
    fulfillment_options: tuple[str, ...]
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

    # Recovery/contact target sourced from Shop configuration
    support_whatsapp_url: str

    # Disponibilidade robusta de datas (nunca oferecer dia fechado):
    # próximas datas em que a loja opera + dias da semana sem expediente.
    available_dates: tuple[str, ...] = ()
    closed_weekdays: tuple[int, ...] = ()

    # Fulfillment contextual hints shown below the pickup/delivery chips
    pickup_hint: str = ""
    delivery_hint: str = ""

    # Provedor de cartão (Stripe/Efí) p/ o storefront dar previsibilidade no
    # checkout ("pagamento seguro via X"). Vazio quando não há provedor real
    # configurado (ex.: mock no dev). Tenant-safe: vem do adapter, não hardcoded.
    card_provider: str = ""


# ──────────────────────────────────────────────────────────────────────
# Builder
# ──────────────────────────────────────────────────────────────────────


def build_checkout(
    *,
    request: HttpRequest,
    channel_ref: str = _DEFAULT_CHANNEL_REF,
    delivery_date: str | None = None,
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
    preselected_address_id: int | None = None
    loyalty_balance_q = 0
    loyalty_value_display: str | None = None

    if customer_info:
        customer_phone = customer_info.phone or ""
        customer_name = customer_info.name or ""
        (
            saved_addresses,
            preselected_address_id,
            loyalty_balance_q,
            loyalty_value_display,
        ) = _load_customer_context(customer_info)

    interaction = InteractionContext.from_request(
        request,
        channel_ref=channel_ref,
        surface_ref="django_penguin",
        target_kind="checkout",
    )
    policy = resolve_channel_policy(interaction.channel_ref)
    payment_methods = _payment_methods(channel_ref)
    pickup_slots, earliest_slot_ref = _pickup_slots(
        cart,
        delivery_date=_delivery_date_from_context(request, delivery_date),
    )
    max_preorder_days, closed_dates, support_whatsapp_url = _shop_config()
    available_dates, closed_weekdays = _availability_dates(max_preorder_days)

    is_authenticated = customer_info is not None
    requires_authentication = _requires_authentication(channel_ref)

    return CheckoutProjection(
        cart=cart,
        customer_phone=customer_phone,
        customer_name=customer_name,
        is_authenticated=is_authenticated,
        requires_authentication=requires_authentication,
        auth_action=_auth_action() if requires_authentication and not is_authenticated else None,
        saved_addresses=saved_addresses,
        preselected_address_id=preselected_address_id,
        payment_methods=payment_methods,
        default_payment_method=payment_methods[0].ref if payment_methods else "cash",
        actions=_checkout_actions(
            policy,
            cart=cart,
            is_authenticated=is_authenticated,
            requires_authentication=requires_authentication,
        ),
        fulfillment_options=policy.fulfillment_types,
        has_pickup="pickup" in policy.fulfillment_types,
        has_delivery="delivery" in policy.fulfillment_types,
        pickup_slots=pickup_slots,
        earliest_slot_ref=earliest_slot_ref,
        loyalty_balance_q=loyalty_balance_q,
        loyalty_value_display=loyalty_value_display,
        max_preorder_days=max_preorder_days,
        closed_dates_json=json.dumps(closed_dates),
        available_dates=available_dates,
        closed_weekdays=closed_weekdays,
        is_debug=settings.DEBUG,
        support_whatsapp_url=support_whatsapp_url,
        pickup_hint="Gratuita",
        delivery_hint="",
        card_provider=_card_provider(),
    )


def _availability_dates(max_preorder_days: int) -> tuple[tuple[str, ...], tuple[int, ...]]:
    """Próximas datas em que a loja opera + dias da semana fechados.

    Fonte da verdade: ``business_calendar`` (horário semanal + feriados/férias).
    Degrada para vazio se algo falhar — a UI cai no fallback de datas.
    """
    try:
        from shopman.shop.services import business_calendar

        dates = business_calendar.available_dates(max_count=3, horizon_days=max_preorder_days)
        return (
            tuple(d.isoformat() for d in dates),
            tuple(business_calendar.closed_weekdays()),
        )
    except Exception:
        logger.debug("checkout_projection_availability_dates_failed", exc_info=True)
        return (), ()


def _card_provider() -> str:
    """Nome amigável do provedor de cartão configurado (Stripe/Efí).

    Derivado do adapter em ``SHOPMAN_PAYMENT_ADAPTERS["card"]`` — tenant-safe,
    nada hardcoded. Mock/sem provedor real → string vazia.
    """
    from django.conf import settings

    path = (getattr(settings, "SHOPMAN_PAYMENT_ADAPTERS", {}) or {}).get("card") or ""
    if "stripe" in path:
        return "Stripe"
    if "efi" in path:
        return "Efí"
    return ""


# ──────────────────────────────────────────────────────────────────────
# Internals
# ──────────────────────────────────────────────────────────────────────


def _load_customer_context(
    customer_info,
) -> tuple[tuple[SavedAddressProjection, ...], int | None, int, str | None]:
    """Return (saved_addresses, preselected_address_id, loyalty_balance_q, loyalty_value_display)."""
    try:
        context = customer_context.checkout_customer_context(customer_info.uuid)
    except Exception:
        logger.debug("checkout_projection_customer_context_failed", exc_info=True)
        return (), None, 0, None

    saved_addresses = tuple(
        SavedAddressProjection(
            id=addr.id,
            formatted_address=addr.formatted_address,
            complement=addr.complement,
            label=addr.label,
            is_default=addr.is_default,
            label_key=addr.label_key,
            label_custom=addr.label_custom,
            route=addr.route,
            street_number=addr.street_number,
            neighborhood=addr.neighborhood,
            city=addr.city,
            state_code=addr.state_code,
            postal_code=addr.postal_code,
            latitude=addr.latitude,
            longitude=addr.longitude,
            place_id=addr.place_id,
            delivery_instructions=addr.delivery_instructions,
        )
        for addr in context.saved_addresses
    )

    loyalty_balance_q = context.loyalty_balance_q
    loyalty_value_display: str | None = None
    if loyalty_balance_q > 0:
        loyalty_value_display = f"R$ {format_money(loyalty_balance_q)}"

    return (
        saved_addresses,
        context.preselected_address_id,
        loyalty_balance_q,
        loyalty_value_display,
    )


def _payment_methods(channel_ref: str) -> tuple[PaymentMethodOptionProjection, ...]:
    """Resolve channel payment methods from ChannelConfig."""
    try:
        from shopman.shop.config import ChannelConfig
        from shopman.shop.models import Channel

        channel = Channel.objects.get(ref=channel_ref)
        methods = ChannelConfig.for_channel(channel).payment.available_methods
    except Exception:
        logger.debug(
            "checkout_projection_payment_methods_failed channel=%s",
            channel_ref,
            exc_info=True,
        )
        methods = ["cash"]

    return tuple(
        PaymentMethodOptionProjection(
            ref=m,
            label=payment_method_label(m),
            is_default=(i == 0),
        )
        for i, m in enumerate(methods)
    )


def _checkout_actions(
    policy: ChannelPolicyResolution,
    *,
    cart: CartProjection,
    is_authenticated: bool,
    requires_authentication: bool,
) -> tuple[Action, ...]:
    auth_blocked = requires_authentication and not is_authenticated
    enabled = policy.can_checkout and not cart.is_empty and not auth_blocked
    reason = ""
    if cart.is_empty:
        reason = "Carrinho vazio."
    elif auth_blocked:
        reason = "Entre por telefone para continuar."
    elif not policy.can_checkout:
        reason = "Checkout indisponível para este canal."

    return (
        Action(
            ref="checkout",
            kind="mutation",
            label="Confirmar pedido",
            priority="primary",
            enabled=enabled,
            reason=reason,
            method="POST",
            href="/api/v1/checkout/",
            payload_schema={
                "required": ["name", "phone", "fulfillment_type", "payment_method"],
                "optional": [
                    "delivery_address",
                    "saved_address_id",
                    "delivery_time_slot",
                    "notes",
                    "use_loyalty",
                ],
            },
            idempotency="required",
        ),
    )


def _requires_authentication(channel_ref: str) -> bool:
    """Storefront checkout currently requires a phone-authenticated customer."""
    return channel_ref == _DEFAULT_CHANNEL_REF


def _auth_action() -> Action:
    return Action(
        ref="checkout_login",
        kind="link",
        label="Entrar por telefone",
        priority="primary",
        href="/login?next=/checkout",
    )


def _pickup_slots(
    cart: CartProjection,
    *,
    delivery_date: str = "",
) -> tuple[tuple[PickupSlotProjection, ...], str | None]:
    """Resolve pickup slots and earliest available slot for the cart."""
    try:
        from shopman.storefront.services.pickup_slots import annotate_slots_for_checkout

        cart_skus = [item.sku for item in cart.items]
        ctx = annotate_slots_for_checkout(cart_skus, delivery_date=delivery_date)
        raw_slots = ctx.get("pickup_slots") or []
        slots = tuple(
            PickupSlotProjection(
                ref=str(s.get("ref") or ""),
                label=str(s.get("label") or ""),
                starts_at=str(s.get("starts_at") or ""),
                enabled=bool(s.get("enabled", True)),
                reason=str(s.get("reason") or ""),
                is_earliest=bool(s.get("is_earliest", False)),
            )
            for s in raw_slots
        )
        earliest = ctx.get("earliest_slot_ref")
        return slots, earliest
    except Exception:
        logger.debug("checkout_projection_slots_failed", exc_info=True)
        return (), None


def _delivery_date_from_context(request: HttpRequest, delivery_date: str | None) -> str:
    if delivery_date is not None:
        return str(delivery_date or "").strip()
    try:
        return str(request.GET.get("delivery_date") or request.POST.get("delivery_date") or "").strip()
    except Exception:
        logger.debug("checkout_projection_delivery_date_failed", exc_info=True)
        return ""


def _shop_config() -> tuple[int, list, str]:
    """Return (max_preorder_days, closed_dates, support_whatsapp_url)."""
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        if shop:
            defaults = shop.defaults or {}
            return (
                int(defaults.get("max_preorder_days", 30)),
                defaults.get("closed_dates", []),
                shop.whatsapp_url,
            )
    except Exception:
        logger.debug("checkout_projection_shop_config_failed", exc_info=True)
    return 30, [], ""


# ──────────────────────────────────────────────────────────────────────
# Validation message builders — render the checkout DATA projections
# (shop.projections.checkout) as the dicts the form/JS consume.
# ──────────────────────────────────────────────────────────────────────


def present_repricing_warnings(changes) -> list[dict]:
    """Render repricing-change data as the warning dicts the checkout shows."""
    if not changes:
        return []
    copy = build_copy("CHECKOUT")
    warnings = []
    for ch in changes:
        current_display = f"R$ {format_money(ch.current_price_q)}"
        message = copy.message(
            "CHECKOUT_REPRICING_MESSAGE",
            "O preço de {name} mudou para {price}. Deseja continuar?",
        ).format(name=ch.name, price=current_display)
        warnings.append({
            "sku": ch.sku,
            "name": ch.name,
            "cart_price_display": f"R$ {format_money(ch.cart_price_q)}",
            "current_price_display": current_display,
            "message": message,
        })
    return warnings


def present_stock_errors(shortfalls) -> list[dict]:
    """Render stock-shortfall data as the error dicts the checkout shows."""
    if not shortfalls:
        return []
    copy = build_copy("CHECKOUT")
    errors = []
    for sf in shortfalls:
        if sf.available_qty > 0:
            message = copy.message(
                "CHECKOUT_STOCK_LIMITED",
                "{name}: disponível {qty} unidade(s) no momento.",
            ).format(name=sf.name, qty=sf.available_qty)
        else:
            message = copy.message(
                "CHECKOUT_STOCK_SOLD_OUT",
                "{name} está esgotado no momento.",
            ).format(name=sf.name)
        errors.append({
            "line_id": sf.line_id,
            "sku": sf.sku,
            "requested_qty": sf.requested_qty,
            "available_qty": sf.available_qty,
            "message": message,
        })
    return errors


__all__ = [
    "CheckoutProjection",
    "build_checkout",
    "present_repricing_warnings",
    "present_stock_errors",
]
