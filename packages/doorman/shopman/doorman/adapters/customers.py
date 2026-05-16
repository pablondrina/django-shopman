"""
AuthCustomerResolver -- Production adapter backed by Guestman.

Implements the CustomerResolver protocol by delegating to
shopman.guestman.services.customer for all customer lookup and creation.

This is the default adapter used when Auth runs alongside Guestman
in the shopman-suite. It translates between Guestman's Customer model
and Auth's AuthCustomerInfo dataclass.

Configure in settings (this is the default):
    DOORMAN = {
        "CUSTOMER_RESOLVER_CLASS": "shopman.doorman.adapters.customers.AuthCustomerResolver",
    }

Requires shopman.guestman to be installed and available on the Python path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from shopman.doorman.protocols.customer import AuthCustomerInfo

if TYPE_CHECKING:
    from shopman.guestman.models import Customer


class AuthCustomerResolver:
    """
    Customer resolver backed by Guestman's customer service layer.

    Each method delegates to shopman.guestman.services.customer and converts
    the returned Customer model instance into an AuthCustomerInfo.
    """

    def get_by_phone(self, phone: str) -> AuthCustomerInfo | None:
        """Lookup customer by phone via Guestman."""
        from shopman.guestman.services import customer as customer_service

        c = customer_service.get_by_phone(phone)
        return self._to_info(c) if c else None

    def get_by_email(self, email: str) -> AuthCustomerInfo | None:
        """Lookup customer by email via Guestman."""
        from shopman.guestman.services import customer as customer_service

        c = customer_service.get_by_email(email)
        return self._to_info(c) if c else None

    def get_by_uuid(self, uuid: UUID) -> AuthCustomerInfo | None:
        """Lookup customer by UUID via Guestman."""
        from shopman.guestman.services import customer as customer_service

        c = customer_service.get_by_uuid(str(uuid))
        return self._to_info(c) if c else None

    def get_by_identifier(self, identifier_type: str, identifier_value: str) -> AuthCustomerInfo | None:
        """Lookup customer by a Guestman external identifier."""
        from shopman.guestman.contrib.identifiers.models import CustomerIdentifier

        if not identifier_type or not identifier_value:
            return None
        ident = (
            CustomerIdentifier.objects.select_related("customer")
            .filter(identifier_type=identifier_type, identifier_value=str(identifier_value))
            .first()
        )
        if not ident or not ident.customer.is_active:
            return None
        return self._to_info(ident.customer)

    def upsert_access_link_customer(self, customer_id, payload: dict) -> AuthCustomerInfo | None:
        """Enrich a known Guestman customer with trusted access-link identity data."""
        from shopman.guestman.contrib.manychat.service import ManychatService
        from shopman.guestman.services import customer as customer_service

        c = customer_service.get_by_uuid(str(customer_id))
        if not c:
            return None

        source_system = "manychat" if payload.get("id") else "access_link"
        c = ManychatService.sync_customer(c, payload, source_system=source_system)
        if not c or not c.is_active:
            return None
        return self._to_info(c)

    def upsert_manychat_subscriber(self, subscriber_data: dict) -> AuthCustomerInfo | None:
        """Sync a ManyChat subscriber and return the linked customer."""
        from shopman.guestman.contrib.manychat.service import ManychatService

        customer, _created = ManychatService.sync_subscriber(subscriber_data)
        if not customer or not customer.is_active:
            return None
        return self._to_info(customer)

    def create_for_phone(self, phone: str) -> AuthCustomerInfo:
        """Create a new customer with the given phone via Guestman."""
        from shopman.guestman.models import Customer
        from shopman.guestman.services import customer as customer_service
        from shopman.guestman.services import identity as identity_service

        c = customer_service.create(
            ref=Customer.generate_ref(),
            first_name="",
            phone=phone,
            source_system="doorman",
        )
        identity_service.ensure_contact_point(
            c,
            type="whatsapp",
            value_normalized=c.phone,
            is_primary=True,
        )
        return self._to_info(c)

    def create_for_email(self, email: str) -> AuthCustomerInfo:
        """Create a new customer with the given email via Guestman."""
        from shopman.guestman.models import ContactPoint, Customer
        from shopman.guestman.services import customer as customer_service
        from shopman.guestman.services import identity as identity_service

        c = customer_service.create(
            ref=Customer.generate_ref(),
            first_name="",
            email=email,
            source_system="doorman",
        )
        identity_service.ensure_contact_point(
            c,
            type=ContactPoint.Type.EMAIL,
            value_normalized=c.email,
            is_primary=True,
        )
        return self._to_info(c)

    @staticmethod
    def _to_info(c: Customer) -> AuthCustomerInfo:
        """Convert a Guestman Customer model to AuthCustomerInfo."""
        from shopman.guestman.models import ContactPoint

        primary_phone = (
            c.contact_points.filter(
                type__in=[ContactPoint.Type.WHATSAPP, ContactPoint.Type.PHONE],
            )
            .order_by("-is_primary", "-is_verified", "-updated_at")
            .values_list("value_normalized", flat=True)
            .first()
        )
        primary_email = (
            c.contact_points.filter(type=ContactPoint.Type.EMAIL)
            .order_by("-is_primary", "-is_verified", "-updated_at")
            .values_list("value_normalized", flat=True)
            .first()
        )

        return AuthCustomerInfo(
            uuid=c.uuid,
            name=c.name,
            phone=primary_phone or c.phone,
            email=primary_email or c.email,
            is_active=c.is_active,
        )
