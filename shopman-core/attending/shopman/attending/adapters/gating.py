"""Attending adapter for Doorman's CustomerResolver protocol."""

from __future__ import annotations

import uuid as uuid_lib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from doorman.protocols.customer import DoormanCustomerInfo

from shopman.attending.models import Customer
from shopman.attending.services import customer as customer_service


class AttendingCustomerResolver:
    """Adapter: Attending implements Doorman's CustomerResolver."""

    def get_by_phone(self, phone: str) -> DoormanCustomerInfo | None:
        c = customer_service.get_by_phone(phone)
        return self._to_info(c) if c else None

    def get_by_email(self, email: str) -> DoormanCustomerInfo | None:
        c = customer_service.get_by_email(email)
        return self._to_info(c) if c else None

    def get_by_uuid(self, uuid) -> DoormanCustomerInfo | None:
        c = customer_service.get_by_uuid(str(uuid))
        return self._to_info(c) if c else None

    def create_for_phone(self, phone: str) -> DoormanCustomerInfo:
        c = customer_service.create(
            ref=f"WEB-{str(uuid_lib.uuid4())[:8].upper()}",
            first_name="",
            phone=phone,
        )
        return self._to_info(c)

    @staticmethod
    def _to_info(c: Customer) -> DoormanCustomerInfo:
        from doorman.protocols.customer import DoormanCustomerInfo

        return DoormanCustomerInfo(
            uuid=c.uuid,
            name=c.name,
            phone=c.phone,
            email=c.email,
            is_active=c.is_active,
        )
