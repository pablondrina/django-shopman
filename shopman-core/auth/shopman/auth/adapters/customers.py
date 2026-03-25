"""
AuthCustomerResolver -- Production adapter backed by Customers.

Implements the CustomerResolver protocol by delegating to
shopman.customers.services.customer for all customer lookup and creation.

This is the default adapter used when Auth runs alongside Customers
in the shopman-suite. It translates between Customers's Customer model
and Auth's AuthCustomerInfo dataclass.

Configure in settings (this is the default):
    AUTH = {
        "CUSTOMER_RESOLVER_CLASS": "shopman.auth.adapters.customers.AuthCustomerResolver",
    }

Requires shopman.customers to be installed and available on the Python path.
"""

from __future__ import annotations

import uuid as uuid_lib
from typing import TYPE_CHECKING
from uuid import UUID

from shopman.auth.protocols.customer import AuthCustomerInfo

if TYPE_CHECKING:
    from shopman.customers.models import Customer


class AuthCustomerResolver:
    """
    Customer resolver backed by Customers's customer service layer.

    Each method delegates to shopman.customers.services.customer and converts
    the returned Customer model instance into an AuthCustomerInfo.
    """

    def get_by_phone(self, phone: str) -> AuthCustomerInfo | None:
        """Lookup customer by phone via Customers."""
        from shopman.customers.services import customer as customer_service

        c = customer_service.get_by_phone(phone)
        return self._to_info(c) if c else None

    def get_by_email(self, email: str) -> AuthCustomerInfo | None:
        """Lookup customer by email via Customers."""
        from shopman.customers.services import customer as customer_service

        c = customer_service.get_by_email(email)
        return self._to_info(c) if c else None

    def get_by_uuid(self, uuid: UUID) -> AuthCustomerInfo | None:
        """Lookup customer by UUID via Customers."""
        from shopman.customers.services import customer as customer_service

        c = customer_service.get_by_uuid(str(uuid))
        return self._to_info(c) if c else None

    def create_for_phone(self, phone: str) -> AuthCustomerInfo:
        """Create a new customer with the given phone via Customers."""
        from shopman.customers.services import customer as customer_service

        c = customer_service.create(
            code=f"WEB-{str(uuid_lib.uuid4())[:8].upper()}",
            first_name="",
            phone=phone,
        )
        return self._to_info(c)

    @staticmethod
    def _to_info(c: "Customer") -> AuthCustomerInfo:
        """Convert a Customers Customer model to AuthCustomerInfo."""
        return AuthCustomerInfo(
            uuid=c.uuid,
            name=c.name,
            phone=c.phone,
            email=c.email,
            is_active=c.is_active,
        )
