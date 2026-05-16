"""Guestman adapter for Doorman's CustomerResolver protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shopman.doorman.protocols.customer import AuthCustomerInfo

from shopman.guestman.models import Customer
from shopman.guestman.services import customer as customer_service
from shopman.guestman.services import identity as identity_service


class CustomerResolver:
    """Adapter: Guestman implements Doorman's CustomerResolver."""

    def get_by_phone(self, phone: str) -> AuthCustomerInfo | None:
        c = customer_service.get_by_phone(phone)
        return self._to_info(c) if c else None

    def get_by_email(self, email: str) -> AuthCustomerInfo | None:
        c = customer_service.get_by_email(email)
        return self._to_info(c) if c else None

    def get_by_uuid(self, uuid) -> AuthCustomerInfo | None:
        c = customer_service.get_by_uuid(str(uuid))
        return self._to_info(c) if c else None

    def get_by_identifier(self, identifier_type: str, identifier_value: str) -> AuthCustomerInfo | None:
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
        c = customer_service.get_by_uuid(str(customer_id))
        if not c:
            return None

        from shopman.guestman.contrib.manychat.service import ManychatService

        source_system = "manychat" if payload.get("id") else "access_link"
        c = ManychatService.sync_customer(c, payload, source_system=source_system)
        if not c or not c.is_active:
            return None
        return self._to_info(c)

    def upsert_manychat_subscriber(self, subscriber_data: dict) -> AuthCustomerInfo | None:
        from shopman.guestman.contrib.manychat.service import ManychatService

        customer, _created = ManychatService.sync_subscriber(subscriber_data)
        if not customer or not customer.is_active:
            return None
        return self._to_info(customer)

    def create_for_phone(self, phone: str) -> AuthCustomerInfo:
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
        from shopman.guestman.models import ContactPoint

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
        from shopman.doorman.protocols.customer import AuthCustomerInfo
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
