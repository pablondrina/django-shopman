"""
NoopCustomerResolver -- Minimal adapter for development and testing.

Implements the CustomerResolver protocol without any external dependency.
Useful for:
- Running Doorman standalone without Guestman
- Unit tests that don't need real customer data
- Local development and rapid prototyping

Behavior:
- get_by_phone / get_by_email / get_by_uuid return a AuthCustomerInfo
  with the input value deterministically mapped to a UUID.
- create_for_phone returns a AuthCustomerInfo using the phone as identity.
- All returned customers are active with empty name/email fields
  (except when looked up by email).

Configure in settings:
    DOORMAN = {
        "CUSTOMER_RESOLVER_CLASS": "shopman.doorman.adapters.noop.NoopCustomerResolver",
    }
"""

from __future__ import annotations

import uuid as uuid_lib
from uuid import UUID

from shopman.doorman.protocols.customer import AuthCustomerInfo, CustomerResolver


class NoopCustomerResolver:
    """
    No-op customer resolver for development and testing.

    Satisfies the CustomerResolver protocol by returning synthetic
    AuthCustomerInfo instances. No database or external service
    is contacted. The customer UUID is derived deterministically
    from the lookup key using UUID5 (namespace: auth).
    """

    # Fixed namespace UUID for deterministic ID generation.
    _NAMESPACE = uuid_lib.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

    def get_by_phone(self, phone: str) -> AuthCustomerInfo | None:
        """Return a synthetic customer for the given phone number."""
        if not phone:
            return None
        return AuthCustomerInfo(
            uuid=self._make_uuid(phone),
            name="",
            phone=phone,
            email=None,
            is_active=True,
        )

    def get_by_email(self, email: str) -> AuthCustomerInfo | None:
        """Return a synthetic customer for the given email address."""
        if not email:
            return None
        return AuthCustomerInfo(
            uuid=self._make_uuid(email),
            name="",
            phone=None,
            email=email,
            is_active=True,
        )

    def get_by_uuid(self, uuid: UUID) -> AuthCustomerInfo | None:
        """Return a synthetic customer for the given UUID."""
        if not uuid:
            return None
        return AuthCustomerInfo(
            uuid=uuid if isinstance(uuid, UUID) else UUID(str(uuid)),
            name="",
            phone=None,
            email=None,
            is_active=True,
        )

    def get_by_identifier(self, identifier_type: str, identifier_value: str) -> AuthCustomerInfo | None:
        """Return a synthetic customer for an external provider identifier."""
        if not identifier_type or not identifier_value:
            return None
        return AuthCustomerInfo(
            uuid=self._make_uuid(f"{identifier_type}:{identifier_value}"),
            name="",
            phone=None,
            email=None,
            is_active=True,
        )

    def upsert_access_link_customer(self, customer_id: UUID, payload: dict) -> AuthCustomerInfo | None:
        """Return a synthetic customer enriched with access-link payload data."""
        if not customer_id:
            return None
        first = payload.get("first_name", "")
        last = payload.get("last_name", "")
        return AuthCustomerInfo(
            uuid=customer_id if isinstance(customer_id, UUID) else UUID(str(customer_id)),
            name=" ".join(part for part in (first, last) if part).strip(),
            phone=payload.get("whatsapp_id"),
            email=payload.get("email"),
            is_active=True,
        )

    def upsert_manychat_subscriber(self, subscriber_data: dict) -> AuthCustomerInfo | None:
        """Return a synthetic customer from a ManyChat subscriber payload."""
        if not subscriber_data or not subscriber_data.get("id"):
            return None
        first = subscriber_data.get("first_name", "")
        last = subscriber_data.get("last_name", "")
        return AuthCustomerInfo(
            uuid=self._make_uuid(f"manychat:{subscriber_data['id']}"),
            name=" ".join(part for part in (first, last) if part).strip(),
            phone=subscriber_data.get("whatsapp_id"),
            email=subscriber_data.get("email"),
            is_active=True,
        )

    def create_for_phone(self, phone: str) -> AuthCustomerInfo:
        """Create and return a synthetic customer for the given phone number."""
        return AuthCustomerInfo(
            uuid=self._make_uuid(phone),
            name="",
            phone=phone,
            email=None,
            is_active=True,
        )

    def create_for_email(self, email: str) -> AuthCustomerInfo:
        """Create and return a synthetic customer for the given email."""
        return AuthCustomerInfo(
            uuid=self._make_uuid(email),
            name="",
            phone=None,
            email=email,
            is_active=True,
        )

    def _make_uuid(self, key: str) -> UUID:
        """Derive a deterministic UUID from a string key."""
        return uuid_lib.uuid5(self._NAMESPACE, key)


# Runtime check that the class satisfies the protocol.
assert isinstance(NoopCustomerResolver(), CustomerResolver)
