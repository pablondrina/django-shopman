"""CustomerProfileProjection — read model for the account page (Fase 3).

Translates a Customer + loyalty account + addresses + order history into
one immutable projection consumed by the ``storefront/account.html``
template.

``build_account``  → full account page projection.

Never imports from ``shopman.storefront.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from django.utils import timezone
from shopman.utils.monetary import format_money

from shopman.shop.projections.types import (
    FOOD_PREFERENCE_OPTIONS,
    NOTIFICATION_CHANNELS,
    FoodPrefProjection,
    NotificationPrefProjection,
    OrderSummaryProjection,
    SavedAddressProjection,
)
from shopman.shop.services import customer_context, customer_orders

logger = logging.getLogger(__name__)

_DEFAULT_CHANNEL_REF = "web"

TAB_OPTIONS: tuple[tuple[str, str], ...] = (
    ("perfil", "Perfil"),
    ("pedidos", "Pedidos"),
    ("fidelidade", "Fidelidade"),
    ("config", "Configurações"),
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
    """Full read model for the storefront account page."""

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
        records = customer_orders.history_summaries_for_customer_ref(customer.ref, limit=10)
        return tuple(
            OrderSummaryProjection(
                ref=r.ref,
                created_at_display=_fmt_datetime(r.created_at),
                total_q=r.total_q,
                total_display=f"R$ {format_money(r.total_q)}",
                status=r.status,
                status_label=r.status_label,
                status_color=r.status_color,
                item_count=r.items_count,
            )
            for r in records
        )
    except Exception:
        logger.debug("account_projection_orders_failed customer=%s", customer.ref, exc_info=True)
        return ()


def _build_notification_prefs(
    customer: AccountCustomer,
) -> tuple[NotificationPrefProjection, ...]:
    try:
        channels = tuple(key for key, _label, _description in NOTIFICATION_CHANNELS)
        enabled_channels = customer_context.enabled_notification_channels(customer.ref, channels)
        return tuple(
            NotificationPrefProjection(
                key=key,
                label=label,
                description=description,
                enabled=key in enabled_channels,
            )
            for key, label, description in NOTIFICATION_CHANNELS
        )
    except Exception:
        logger.debug(
            "account_projection_notif_prefs_failed customer=%s",
            customer.ref,
            exc_info=True,
        )
        return tuple(
            NotificationPrefProjection(key=key, label=label, description=desc, enabled=False)
            for key, label, desc in NOTIFICATION_CHANNELS
        )


def _build_food_prefs(customer: AccountCustomer) -> tuple[FoodPrefProjection, ...]:
    try:
        active_keys = customer_context.active_preference_keys(customer.ref, "alimentar")
        return tuple(
            FoodPrefProjection(key=key, label=label, is_active=key in active_keys)
            for key, label in FOOD_PREFERENCE_OPTIONS
        )
    except Exception:
        logger.debug(
            "account_projection_food_prefs_failed customer=%s",
            customer.ref,
            exc_info=True,
        )
        return tuple(
            FoodPrefProjection(key=key, label=label, is_active=False)
            for key, label in FOOD_PREFERENCE_OPTIONS
        )


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
]
