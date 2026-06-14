"""Account — storefront Presentation.

Translates a Customer + loyalty account + addresses + order history into one
immutable projection consumed by the ``storefront/account.html`` template, plus
the API-ready order-history dicts the account REST surface serializes. Money is
formatted here, status labels/colours resolved here, dates formatted here —
**no policy**. The order list arrives sealed from the data Projection
(``shop.projections.customer``); customer context (loyalty/addresses/consent)
arrives from ``shop.projections.customer_context`` (clean read helpers).

Never imports from ``shopman.storefront.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from django.utils import timezone

from shopman.shop.projections import customer as customer_projection
from shopman.shop.projections import customer_context
from shopman.shop.projections.types import SavedAddressProjection
from shopman.storefront.presentation.order_history import present_summary
from shopman.storefront.presentation.status import status_tone
from shopman.storefront.presentation.types import (
    FoodPrefProjection,
    NotificationPrefProjection,
    OrderSummaryProjection,
)

logger = logging.getLogger(__name__)

_DEFAULT_CHANNEL_REF = "web"

TAB_OPTIONS: tuple[tuple[str, str], ...] = (
    ("perfil", "Perfil"),
    ("pedidos", "Pedidos"),
    ("fidelidade", "Fidelidade"),
    ("config", "Configurações"),
)

# Display catalogs (key → pt-BR label/description). The set of consent channels
# is the domain registry NOTIFICATION_CONSENT_CHANNELS in shop.services.account;
# here we add the customer-facing copy for each.
NOTIFICATION_CHANNELS: tuple[tuple[str, str, str], ...] = (
    ("whatsapp", "WhatsApp", "Receber atualizações de pedidos via WhatsApp"),
    ("email", "Email", "Receber novidades e promoções por email"),
    ("sms", "SMS", "Receber notificações por SMS"),
    ("push", "Push", "Notificações push no navegador"),
)

FOOD_PREFERENCE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("sem_gluten", "Sem Glúten"),
    ("sem_lactose", "Sem Lactose"),
    ("vegano", "Vegano"),
    ("vegetariano", "Vegetariano"),
    ("sem_acucar", "Sem Açúcar"),
    ("sem_nozes", "Sem Nozes"),
    ("organico", "Orgânico"),
    ("integral", "Integral"),
)


def present_notification_prefs(enabled_channels) -> tuple[NotificationPrefProjection, ...]:
    """Map the enabled-channel set onto the display catalog."""
    enabled = set(enabled_channels)
    return tuple(
        NotificationPrefProjection(key=key, label=label, description=description, enabled=key in enabled)
        for key, label, description in NOTIFICATION_CHANNELS
    )


def present_food_prefs(active_keys) -> tuple[FoodPrefProjection, ...]:
    """Map the active-preference set onto the display catalog."""
    active = set(active_keys)
    return tuple(
        FoodPrefProjection(key=key, label=label, is_active=key in active)
        for key, label in FOOD_PREFERENCE_OPTIONS
    )


class AccountCustomer(Protocol):
    """Customer shape required by the account projection."""

    ref: str
    name: str
    first_name: str
    phone: str
    email: str
    birthday: object | None


# ──────────────────────────────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LoyaltyTransactionProjection:
    """A single loyalty transaction as displayed in the account page."""

    points: int
    description: str
    date_display: str   # "15/04"
    is_credit: bool     # True for positive points


@dataclass(frozen=True)
class LoyaltyProjection:
    """Customer loyalty account summary embedded in CustomerProfileProjection."""

    tier: str          # "bronze", "silver", "gold", "platinum"
    tier_display: str  # display via get_tier_display()
    points_balance: int
    stamps_current: int
    stamps_target: int
    stamps_completed: int
    stamps_range: tuple[int, ...]   # (1, 2, …, stamps_target)
    transactions: tuple[LoyaltyTransactionProjection, ...]


@dataclass(frozen=True)
class CustomerProfileProjection:
    """Full projection for the storefront account page."""

    customer_ref: str
    customer_name: str          # full name (or empty)
    customer_first_name: str
    customer_phone: str         # raw phone, templates use |format_phone
    customer_email: str
    customer_birthday_display: str | None  # "15/04/1990" or None

    loyalty: LoyaltyProjection | None

    saved_addresses: tuple[SavedAddressProjection, ...]
    recent_orders: tuple[OrderSummaryProjection, ...]

    notification_prefs: tuple[NotificationPrefProjection, ...]
    food_pref_options: tuple[FoodPrefProjection, ...]

    tab_options: tuple[tuple[str, str], ...]


# ──────────────────────────────────────────────────────────────────────
# API-ready order history (account REST surface)
# ──────────────────────────────────────────────────────────────────────


def order_history_for_customer(
    *,
    customer_ref: str | None = None,
    phone: str | None = None,
    filter_param: str = "todos",
    limit: int = 20,
) -> list[dict]:
    """Return API-ready customer order history for account surfaces."""
    summaries = customer_projection.history_summaries_for_customer(
        customer_ref=customer_ref,
        phone=phone,
        filter_param=filter_param,
        limit=limit,
    )
    rows: list[dict] = []
    for summary in summaries:
        rendered = present_summary(summary)
        rows.append(
            {
                "ref": rendered.ref,
                "created_at": summary.created_at,
                "created_at_display": rendered.created_at_display,
                "total_display": rendered.total_display,
                "status": rendered.status,
                "status_label": rendered.status_label,
                "status_color": rendered.status_color,
                "status_tone": status_tone(rendered.status),
                "item_count": rendered.item_count,
            }
        )
    return rows


def order_history_for_phone(
    phone: str,
    *,
    filter_param: str = "todos",
    limit: int = 20,
) -> list[dict]:
    """Return API-ready customer order history for the authenticated account API."""
    return order_history_for_customer(
        phone=phone,
        filter_param=filter_param,
        limit=limit,
    )


# ──────────────────────────────────────────────────────────────────────
# Builder
# ──────────────────────────────────────────────────────────────────────


def build_account(
    customer: AccountCustomer,
    *,
    channel_ref: str = _DEFAULT_CHANNEL_REF,
) -> CustomerProfileProjection:
    """Build a ``CustomerProfileProjection`` for the given customer.

    Always returns a projection. Missing services (loyalty down, etc.)
    degrade gracefully to empty/None values.
    """
    birthday_display: str | None = None
    if customer.birthday:
        try:
            birthday_display = customer.birthday.strftime("%d/%m/%Y")
        except Exception:
            logger.debug(
                "account_projection_birthday_format_failed customer=%s",
                customer.ref,
                exc_info=True,
            )

    loyalty = _build_loyalty(customer)
    saved_addresses = _build_addresses(customer)
    recent_orders = _build_recent_orders(customer)
    notification_prefs = _build_notification_prefs(customer)
    food_pref_options = _build_food_prefs(customer)

    return CustomerProfileProjection(
        customer_ref=customer.ref,
        customer_name=customer.name or "",
        customer_first_name=customer.first_name or "",
        customer_phone=customer.phone or "",
        customer_email=customer.email or "",
        customer_birthday_display=birthday_display,
        loyalty=loyalty,
        saved_addresses=saved_addresses,
        recent_orders=recent_orders,
        notification_prefs=notification_prefs,
        food_pref_options=food_pref_options,
        tab_options=TAB_OPTIONS,
    )


# ──────────────────────────────────────────────────────────────────────
# Internals
# ──────────────────────────────────────────────────────────────────────


def _build_loyalty(customer: AccountCustomer) -> LoyaltyProjection | None:
    """Return loyalty projection, or None when unavailable."""
    try:
        account = customer_context.loyalty_account(customer.ref, transaction_limit=5)
        if not account:
            return None

        transactions = tuple(
            LoyaltyTransactionProjection(
                points=t.points,
                description=t.description,
                date_display=timezone.localtime(t.created_at).strftime("%d/%m"),
                is_credit=t.points > 0,
            )
            for t in account.transactions
        )
        stamps_range: tuple[int, ...] = ()
        if account.stamps_target > 0:
            stamps_range = tuple(range(1, account.stamps_target + 1))

        return LoyaltyProjection(
            tier=account.tier,
            tier_display=account.tier_display,
            points_balance=account.points_balance,
            stamps_current=account.stamps_current,
            stamps_target=account.stamps_target,
            stamps_completed=account.stamps_completed,
            stamps_range=stamps_range,
            transactions=transactions,
        )
    except Exception:
        logger.debug("account_projection_loyalty_failed customer=%s", customer.ref, exc_info=True)
        return None


def _build_addresses(customer: AccountCustomer) -> tuple[SavedAddressProjection, ...]:
    try:
        return tuple(
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
            for addr in customer_context.saved_addresses(customer.ref)
        )
    except Exception:
        logger.debug("account_projection_addresses_failed customer=%s", customer.ref, exc_info=True)
        return ()


def _build_recent_orders(
    customer: AccountCustomer,
) -> tuple[OrderSummaryProjection, ...]:
    try:
        records = customer_projection.history_summaries_for_customer(
            customer_ref=customer.ref,
            phone=customer.phone,
            limit=10,
        )
        return tuple(present_summary(r) for r in records)
    except Exception:
        logger.debug("account_projection_orders_failed customer=%s", customer.ref, exc_info=True)
        return ()


def _build_notification_prefs(
    customer: AccountCustomer,
) -> tuple[NotificationPrefProjection, ...]:
    try:
        channels = tuple(key for key, _label, _description in NOTIFICATION_CHANNELS)
        enabled_channels = customer_context.enabled_notification_channels(customer.ref, channels)
        return present_notification_prefs(enabled_channels)
    except Exception:
        logger.debug(
            "account_projection_notif_prefs_failed customer=%s",
            customer.ref,
            exc_info=True,
        )
        return present_notification_prefs(())


def _build_food_prefs(customer: AccountCustomer) -> tuple[FoodPrefProjection, ...]:
    try:
        active_keys = customer_context.active_preference_keys(customer.ref, "alimentar")
        return present_food_prefs(active_keys)
    except Exception:
        logger.debug(
            "account_projection_food_prefs_failed customer=%s",
            customer.ref,
            exc_info=True,
        )
        return present_food_prefs(())


def _fmt_datetime(dt) -> str:
    """Format a datetime as 'DD/MM/AAAA às HH:MM'."""
    try:
        local = timezone.localtime(dt)
        return local.strftime("%d/%m/%Y às %H:%M")
    except Exception:
        logger.debug("account_projection_datetime_format_failed dt=%r", dt, exc_info=True)
        return str(dt)


__all__ = [
    "FOOD_PREFERENCE_OPTIONS",
    "NOTIFICATION_CHANNELS",
    "TAB_OPTIONS",
    "CustomerProfileProjection",
    "LoyaltyProjection",
    "LoyaltyTransactionProjection",
    "build_account",
    "order_history_for_customer",
    "order_history_for_phone",
]
