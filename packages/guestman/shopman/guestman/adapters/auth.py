"""Guestman adapter for Doorman's CustomerResolver protocol."""

from __future__ import annotations

import uuid as uuid_lib
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
