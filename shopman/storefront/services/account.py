"""Storefront account command service.

Views keep HTTP, HTMX rendering, and permission response details here; Guestman
commands live behind this facade.
"""

from __future__ import annotations

import hashlib
import logging

from shopman.shop.projections.types import FoodPrefProjection, NotificationPrefProjection
from shopman.storefront.projections.account import FOOD_PREFERENCE_OPTIONS, NOTIFICATION_CHANNELS

logger = logging.getLogger(__name__)


def get_authenticated_customer(request):
    """Return the authenticated Customer model instance, or None."""
    customer_info = getattr(request, "customer", None)
    if customer_info is None:
        return None

    from shopman.guestman.services import customer as customer_service

    return customer_service.get_by_uuid(customer_info.uuid)


def addresses(customer_ref: str):
    from shopman.guestman.services import address as address_service

    return address_service.addresses(customer_ref)


def get_address(customer_ref: str, pk: int):
    from shopman.guestman.services import address as address_service

    return address_service.get_address(customer_ref, pk)


def address_belongs_to_other_customer(customer_ref: str, pk: int) -> bool:
    from shopman.guestman.services import address as address_service

    return address_service.address_belongs_to_other_customer(customer_ref, pk)


def add_address(customer_ref: str, intent):
    from shopman.guestman.services import address as address_service

    return address_service.add_address(
        customer_ref=customer_ref,
        label=intent.label,
        label_custom=intent.label_custom,
        formatted_address=intent.formatted_address,
        place_id=intent.place_id,
        coordinates=intent.coordinates,
        complement=intent.complement,
        delivery_instructions=intent.delivery_instructions,
        is_default=intent.is_default,
        components={
            "route": intent.route,
            "street_number": intent.street_number,
            "neighborhood": intent.neighborhood,
            "city": intent.city,
            "state_code": intent.state_code,
            "postal_code": intent.postal_code,
        },
    )


def update_address(customer_ref: str, pk: int, intent) -> None:
    from shopman.guestman.services import address as address_service

    fields: dict = {
        "label": intent.label,
        "label_custom": intent.label_custom,
        "formatted_address": intent.formatted_address,
        "route": intent.route,
        "street_number": intent.street_number,
        "neighborhood": intent.neighborhood,
        "city": intent.city,
        "state_code": intent.state_code,
        "postal_code": intent.postal_code,
        "complement": intent.complement,
        "delivery_instructions": intent.delivery_instructions,
        "place_id": intent.place_id,
    }
    if intent.coordinates is not None:
        fields["latitude"] = intent.coordinates[0]
        fields["longitude"] = intent.coordinates[1]
        fields["is_verified"] = True

    address_service.update_address(customer_ref, pk, **fields)


def update_address_label(customer_ref: str, pk: int, *, label: str, label_custom: str) -> None:
    from shopman.guestman.services import address as address_service

    address_service.update_address(customer_ref, pk, label=label, label_custom=label_custom)


def delete_address(customer_ref: str, pk: int) -> None:
    from shopman.guestman.services import address as address_service

    address_service.delete_address(customer_ref, pk)


def set_default_address(customer_ref: str, pk: int) -> None:
    from shopman.guestman.services import address as address_service

    address_service.set_default_address(customer_ref, pk)


def update_profile(customer_ref: str, intent):
    from shopman.guestman.services import customer as customer_service

    return customer_service.update(
        customer_ref,
        first_name=intent.first_name,
        last_name=intent.last_name,
        email=intent.email,
        birthday=intent.birthday,
    )


def preferences(customer_ref: str, category: str | None = None):
    from shopman.guestman import PreferenceService

    return PreferenceService.get_preferences(customer_ref, category)


def active_food_keys(customer_ref: str) -> set[str]:
    return {pref.key for pref in preferences(customer_ref, "alimentar")}


def toggle_food_preference(customer_ref: str, key: str) -> tuple[FoodPrefProjection, ...]:
    from shopman.guestman import PreferenceService

    existing = PreferenceService.get_preference(customer_ref, "alimentar", key)
    if existing is not None:
        PreferenceService.delete_preference(customer_ref, "alimentar", key)
    else:
        PreferenceService.set_preference(
            customer_ref,
            "alimentar",
            key,
            value=True,
            preference_type="restriction",
            source="storefront_settings",
        )

    active_keys = active_food_keys(customer_ref)
    return tuple(
        FoodPrefProjection(key=option_key, label=label, is_active=option_key in active_keys)
        for option_key, label in FOOD_PREFERENCE_OPTIONS
    )


def toggle_notification_consent(
    customer_ref: str,
    channel: str,
    *,
    ip_address: str = "",
) -> tuple[NotificationPrefProjection, ...]:
    from shopman.guestman import ConsentService

    if ConsentService.has_consent(customer_ref, channel):
        ConsentService.revoke_consent(customer_ref, channel)
    else:
        ConsentService.grant_consent(
            customer_ref,
            channel,
            source="storefront_settings",
            legal_basis="consent",
            ip_address=ip_address,
        )

    return notification_preferences(customer_ref)


def notification_preferences(customer_ref: str) -> tuple[NotificationPrefProjection, ...]:
    from shopman.guestman import ConsentService

    return tuple(
        NotificationPrefProjection(
            key=key,
            label=label,
            description=description,
            enabled=ConsentService.has_consent(customer_ref, key),
        )
        for key, label, description in NOTIFICATION_CHANNELS
    )


def export_customer_data(customer) -> dict:
    data = {
        "customer": {
            "ref": customer.ref,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "phone": customer.phone,
            "email": customer.email,
            "birthday": str(customer.birthday) if customer.birthday else None,
            "created_at": customer.created_at.isoformat(),
        },
        "addresses": [
            {
                "label": addr.label,
                "formatted_address": addr.formatted_address,
                "route": addr.route,
                "street_number": addr.street_number,
                "neighborhood": addr.neighborhood,
                "city": addr.city,
                "complement": addr.complement,
                "delivery_instructions": addr.delivery_instructions,
                "is_default": addr.is_default,
            }
            for addr in addresses(customer.ref)
        ],
    }

    from shopman.orderman.services import CustomerOrderHistoryService

    orders = CustomerOrderHistoryService.list_customer_orders(customer.ref, limit=100)
    data["orders"] = [
        {
            "ref": order.order_ref,
            "status": order.status,
            "total_q": order.total_q,
            "created_at": order.ordered_at.isoformat(),
            "items": order.items,
        }
        for order in orders
    ]

    data["preferences"] = [
        {
            "category": pref.category,
            "key": pref.key,
            "value": pref.value,
            "preference_type": pref.preference_type,
        }
        for pref in preferences(customer.ref)
    ]

    from shopman.guestman import ConsentService

    data["consents"] = [
        {
            "channel": consent.channel,
            "status": consent.status,
            "consented_at": consent.consented_at,
            "revoked_at": consent.revoked_at,
        }
        for consent in ConsentService.get_consents(customer.ref)
    ]

    try:
        from shopman.guestman import LoyaltyService

        account = LoyaltyService.get_account(customer.ref)
        if account:
            data["loyalty"] = {
                "tier": account.tier,
                "points_balance": account.points_balance,
                "lifetime_points": account.lifetime_points,
                "stamps_current": account.stamps_current,
            }
            txns = LoyaltyService.get_transactions(customer.ref, limit=100)
            data["loyalty"]["transactions"] = [
                {
                    "type": txn.transaction_type,
                    "points": txn.points,
                    "description": txn.description,
                    "created_at": txn.created_at.isoformat(),
                }
                for txn in txns
            ]
    except Exception:
        logger.warning("data_export_loyalty_failed", exc_info=True)

    return data


def anonymize_customer(customer) -> tuple[str, str]:
    """Anonymize personal data and return original ref + phone hash."""
    original_ref = customer.ref
    original_phone = customer.phone or ""
    phone_hash = hashlib.sha256(original_phone.encode()).hexdigest()[:12]

    from shopman.guestman import ConsentService
    from shopman.guestman.services import address as address_service

    for channel in ("whatsapp", "email", "sms", "push"):
        try:
            ConsentService.revoke_consent(original_ref, channel)
        except Exception:
            logger.warning("consent_revoke_failed channel=%s", channel, exc_info=True)

    try:
        address_service.delete_all_addresses(original_ref)
    except Exception:
        logger.warning("address_cleanup_failed customer=%s", original_ref, exc_info=True)

    customer.first_name = "Anonimizado"
    customer.last_name = ""
    customer.email = ""
    customer.phone = ""
    customer.birthday = None
    customer.notes = ""
    customer.is_active = False
    customer.save()

    return original_ref, phone_hash
