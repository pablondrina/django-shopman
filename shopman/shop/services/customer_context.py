"""Canonical customer read helpers for storefront projections.

This module is the shop-layer boundary for Guestman-backed customer context:
addresses, loyalty, consent, preferences, and authenticated customer lookup.
Surface projections may map these neutral read models into template-specific
dataclasses, but should not read Guestman directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CustomerAddressContext:
    """A saved address with picker-ready structured fields."""

    id: int
    formatted_address: str
    complement: str
    label: str
    is_default: bool
    route: str = ""
    street_number: str = ""
    neighborhood: str = ""
    city: str = ""
    state_code: str = ""
    postal_code: str = ""
    latitude: float | None = None
    longitude: float | None = None
    place_id: str = ""
    delivery_instructions: str = ""


@dataclass(frozen=True)
class LoyaltyTransactionContext:
    """A single loyalty transaction without storefront formatting."""

    points: int
    description: str
    created_at: Any


@dataclass(frozen=True)
class LoyaltyAccountContext:
    """Customer loyalty summary without storefront formatting."""

    tier: str
    tier_display: str
    points_balance: int
    stamps_current: int
    stamps_target: int
    stamps_completed: int
    transactions: tuple[LoyaltyTransactionContext, ...]


@dataclass(frozen=True)
class CheckoutCustomerContext:
    """Customer context needed by the checkout projection."""

    customer_ref: str | None
    saved_addresses: tuple[CustomerAddressContext, ...]
    preselected_address_id: int | None
    loyalty_balance_q: int


def customer_ref_by_uuid(customer_uuid: Any) -> str | None:
    """Resolve an authenticated customer UUID to the canonical customer ref."""
    if not customer_uuid:
        return None

    try:
        from shopman.guestman.services import customer as customer_service

        customer = customer_service.get_by_uuid(customer_uuid)
    except Exception:
        logger.debug(
            "customer_context_customer_lookup_failed uuid=%s",
            customer_uuid,
            exc_info=True,
        )
        return None

    return customer.ref if customer is not None else None


def saved_addresses(customer_ref: str) -> tuple[CustomerAddressContext, ...]:
    """Return saved addresses for a customer, degrading to an empty tuple."""
    try:
        from shopman.guestman.services import address as address_service

        return tuple(_address_context(addr) for addr in address_service.addresses(customer_ref))
    except Exception:
        logger.debug(
            "customer_context_addresses_failed customer=%s",
            customer_ref,
            exc_info=True,
        )
        return ()


def suggested_address_id(customer_ref: str) -> int | None:
    """Return the suggested checkout address id, if any."""
    try:
        from shopman.guestman.services import address as address_service

        suggested = address_service.suggest_address(customer_ref)
    except Exception:
        logger.debug(
            "customer_context_suggest_address_failed customer=%s",
            customer_ref,
            exc_info=True,
        )
        return None

    return suggested.id if suggested is not None else None


def loyalty_account(
    customer_ref: str,
    *,
    transaction_limit: int = 5,
) -> LoyaltyAccountContext | None:
    """Return loyalty account context, or None when unavailable/not enrolled."""
    try:
        from shopman.guestman.contrib.loyalty import LoyaltyService

        account = LoyaltyService.get_account(customer_ref)
    except Exception:
        logger.debug(
            "customer_context_loyalty_account_failed customer=%s",
            customer_ref,
            exc_info=True,
        )
        return None

    if account is None:
        return None

    transactions = loyalty_transactions(customer_ref, limit=transaction_limit)
    return LoyaltyAccountContext(
        tier=account.tier,
        tier_display=account.get_tier_display(),
        points_balance=account.points_balance,
        stamps_current=account.stamps_current,
        stamps_target=account.stamps_target,
        stamps_completed=account.stamps_completed,
        transactions=transactions,
    )


def loyalty_transactions(
    customer_ref: str,
    *,
    limit: int = 5,
) -> tuple[LoyaltyTransactionContext, ...]:
    """Return loyalty transactions, degrading independently from the account."""
    try:
        from shopman.guestman.contrib.loyalty import LoyaltyService

        transactions = LoyaltyService.get_transactions(customer_ref, limit=limit)
    except Exception:
        logger.debug(
            "customer_context_loyalty_transactions_failed customer=%s",
            customer_ref,
            exc_info=True,
        )
        return ()

    return tuple(
        LoyaltyTransactionContext(
            points=txn.points,
            description=txn.description or "",
            created_at=txn.created_at,
        )
        for txn in transactions
    )


def loyalty_balance(customer_ref: str) -> int:
    """Return checkout loyalty balance, degrading to zero."""
    try:
        from shopman.guestman.contrib.loyalty import LoyaltyService

        return max(0, LoyaltyService.get_balance(customer_ref))
    except Exception:
        logger.debug(
            "customer_context_loyalty_balance_failed customer=%s",
            customer_ref,
            exc_info=True,
        )
        return 0


def enabled_notification_channels(
    customer_ref: str,
    channels: tuple[str, ...],
) -> frozenset[str]:
    """Return channels with active consent; failed channel checks become false."""
    try:
        from shopman.guestman.contrib.consent import ConsentService
    except Exception:
        logger.debug(
            "customer_context_consent_import_failed customer=%s",
            customer_ref,
            exc_info=True,
        )
        return frozenset()

    enabled: set[str] = set()
    for channel in channels:
        try:
            if ConsentService.has_consent(customer_ref, channel):
                enabled.add(channel)
        except Exception:
            logger.debug(
                "customer_context_consent_channel_failed customer=%s channel=%s",
                customer_ref,
                channel,
                exc_info=True,
            )
    return frozenset(enabled)


def active_preference_keys(customer_ref: str, category: str) -> frozenset[str]:
    """Return active preference keys for a category, degrading to empty."""
    try:
        from shopman.guestman.contrib.preferences import PreferenceService

        preferences = PreferenceService.get_preferences(customer_ref, category)
    except Exception:
        logger.debug(
            "customer_context_preferences_failed customer=%s category=%s",
            customer_ref,
            category,
            exc_info=True,
        )
        return frozenset()

    return frozenset(pref.key for pref in preferences)


def checkout_customer_context(customer_uuid: Any) -> CheckoutCustomerContext:
    """Return all customer read context needed by checkout."""
    customer_ref = customer_ref_by_uuid(customer_uuid)
    if customer_ref is None:
        return CheckoutCustomerContext(
            customer_ref=None,
            saved_addresses=(),
            preselected_address_id=None,
            loyalty_balance_q=0,
        )

    return CheckoutCustomerContext(
        customer_ref=customer_ref,
        saved_addresses=saved_addresses(customer_ref),
        preselected_address_id=suggested_address_id(customer_ref),
        loyalty_balance_q=loyalty_balance(customer_ref),
    )


def _address_context(addr: Any) -> CustomerAddressContext:
    return CustomerAddressContext(
        id=addr.id,
        formatted_address=addr.formatted_address or "",
        complement=addr.complement or "",
        label=addr.display_label or addr.formatted_address or "",
        is_default=addr.is_default,
        route=addr.route or "",
        street_number=addr.street_number or "",
        neighborhood=addr.neighborhood or "",
        city=addr.city or "",
        state_code=addr.state_code or "",
        postal_code=addr.postal_code or "",
        latitude=float(addr.latitude) if addr.latitude is not None else None,
        longitude=float(addr.longitude) if addr.longitude is not None else None,
        place_id=addr.place_id or "",
        delivery_instructions=addr.delivery_instructions or "",
    )
