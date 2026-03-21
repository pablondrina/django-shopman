"""
AttendingCustomerResolver -- Production adapter backed by Guestman.

Implements the CustomerResolver protocol by delegating to
guestman.services.customer for all customer lookup and creation.

This is the default adapter used when Gating runs alongside Guestman
in the shopman-suite. It translates between Guestman's Customer model
and Gating's GatingCustomerInfo dataclass.

Configure in settings (this is the default):
    GATING = {
        "CUSTOMER_RESOLVER_CLASS": "shopman.gating.adapters.guestman.AttendingCustomerResolver",
    }

Requires guestman to be installed and available on the Python path.
"""

from __future__ import annotations

import uuid as uuid_lib
from typing import TYPE_CHECKING
from uuid import UUID

from shopman.gating.protocols.customer import CustomerResolver, GatingCustomerInfo

if TYPE_CHECKING:
    from shopman.attending.models import Customer


class AttendingCustomerResolver:
    """
    Customer resolver backed by Guestman's customer service layer.

    Each method delegates to guestman.services.customer and converts
    the returned Customer model instance into a GatingCustomerInfo.
    """

    def get_by_phone(self, phone: str) -> GatingCustomerInfo | None:
        """Lookup customer by phone via Guestman."""
        from shopman.attending.services import customer as customer_service

        c = customer_service.get_by_phone(phone)
        return self._to_info(c) if c else None

    def get_by_email(self, email: str) -> GatingCustomerInfo | None:
        """Lookup customer by email via Guestman."""
        from shopman.attending.services import customer as customer_service

        c = customer_service.get_by_email(email)
        return self._to_info(c) if c else None

    def get_by_uuid(self, uuid: UUID) -> GatingCustomerInfo | None:
        """Lookup customer by UUID via Guestman."""
        from shopman.attending.services import customer as customer_service

        c = customer_service.get_by_uuid(str(uuid))
        return self._to_info(c) if c else None

    def create_for_phone(self, phone: str) -> GatingCustomerInfo:
        """Create a new customer with the given phone via Guestman."""
        from shopman.attending.services import customer as customer_service

        c = customer_service.create(
            code=f"WEB-{str(uuid_lib.uuid4())[:8].upper()}",
            first_name="",
            phone=phone,
        )
        return self._to_info(c)

    @staticmethod
    def _to_info(c: "Customer") -> GatingCustomerInfo:
        """Convert a Guestman Customer model to GatingCustomerInfo."""
        return GatingCustomerInfo(
            uuid=c.uuid,
            name=c.name,
            phone=c.phone,
            email=c.email,
            is_active=c.is_active,
        )
