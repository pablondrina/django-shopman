"""
NoopCustomerResolver -- Minimal adapter for development and testing.

Implements the CustomerResolver protocol without any external dependency.
Useful for:
- Running Gating standalone without Guestman
- Unit tests that don't need real customer data
- Local development and rapid prototyping

Behavior:
- get_by_phone / get_by_email / get_by_uuid return a GatingCustomerInfo
  with the input value deterministically mapped to a UUID.
- create_for_phone returns a GatingCustomerInfo using the phone as identity.
- All returned customers are active with empty name/email fields
  (except when looked up by email).

Configure in settings:
    GATING = {
        "CUSTOMER_RESOLVER_CLASS": "shopman.gating.adapters.noop.NoopCustomerResolver",
    }
"""

from __future__ import annotations

import uuid as uuid_lib
from uuid import UUID

from shopman.gating.protocols.customer import CustomerResolver, GatingCustomerInfo


class NoopCustomerResolver:
    """
    No-op customer resolver for development and testing.

    Satisfies the CustomerResolver protocol by returning synthetic
    GatingCustomerInfo instances. No database or external service
    is contacted. The customer UUID is derived deterministically
    from the lookup key using UUID5 (namespace: doorman).
    """

    # Fixed namespace UUID for deterministic ID generation.
    _NAMESPACE = uuid_lib.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

    def get_by_phone(self, phone: str) -> GatingCustomerInfo | None:
        """Return a synthetic customer for the given phone number."""
        if not phone:
            return None
        return GatingCustomerInfo(
            uuid=self._make_uuid(phone),
            name="",
            phone=phone,
            email=None,
            is_active=True,
        )

    def get_by_email(self, email: str) -> GatingCustomerInfo | None:
        """Return a synthetic customer for the given email address."""
        if not email:
            return None
        return GatingCustomerInfo(
            uuid=self._make_uuid(email),
            name="",
            phone=None,
            email=email,
            is_active=True,
        )

    def get_by_uuid(self, uuid: UUID) -> GatingCustomerInfo | None:
        """Return a synthetic customer for the given UUID."""
        if not uuid:
            return None
        return GatingCustomerInfo(
            uuid=uuid if isinstance(uuid, UUID) else UUID(str(uuid)),
            name="",
            phone=None,
            email=None,
            is_active=True,
        )

    def create_for_phone(self, phone: str) -> GatingCustomerInfo:
        """Create and return a synthetic customer for the given phone number."""
        return GatingCustomerInfo(
            uuid=self._make_uuid(phone),
            name="",
            phone=phone,
            email=None,
            is_active=True,
        )

    def _make_uuid(self, key: str) -> UUID:
        """Derive a deterministic UUID from a string key."""
        return uuid_lib.uuid5(self._NAMESPACE, key)


# Runtime check that the class satisfies the protocol.
assert isinstance(NoopCustomerResolver(), CustomerResolver)
