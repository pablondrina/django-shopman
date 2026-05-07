"""
Built-in customer resolvers for Doorman.

The default resolver (NoopCustomerResolver) raises NotImplementedError, which
forces the integrator to configure a real resolver via DOORMAN["CUSTOMER_RESOLVER_CLASS"].

When using Guestman, set:

    DOORMAN = {
        "CUSTOMER_RESOLVER_CLASS": "shopman.guestman.adapters.auth.CustomerResolver",
    }
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .protocols.customer import AuthCustomerInfo


class NoopCustomerResolver:
    """
    Default resolver — raises NotImplementedError on every call.

    Replace via DOORMAN["CUSTOMER_RESOLVER_CLASS"] with a real implementation.
    When using shopman-guestman, use "shopman.guestman.adapters.auth.CustomerResolver".
    """

    _msg = (
        "No CustomerResolver configured. "
        "Set DOORMAN['CUSTOMER_RESOLVER_CLASS'] to a class implementing "
        "shopman.doorman.protocols.customer.CustomerResolver. "
        "If you are using shopman-guestman, use "
        "'shopman.guestman.adapters.auth.CustomerResolver'."
    )

    def get_by_phone(self, phone: str) -> AuthCustomerInfo | None:
        raise NotImplementedError(self._msg)

    def get_by_email(self, email: str) -> AuthCustomerInfo | None:
        raise NotImplementedError(self._msg)

    def get_by_uuid(self, uuid) -> AuthCustomerInfo | None:
        raise NotImplementedError(self._msg)

    def get_by_identifier(self, identifier_type: str, identifier_value: str) -> AuthCustomerInfo | None:
        raise NotImplementedError(self._msg)

    def upsert_access_link_customer(self, customer_id, payload: dict) -> AuthCustomerInfo | None:
        raise NotImplementedError(self._msg)

    def upsert_manychat_subscriber(self, subscriber_data: dict) -> AuthCustomerInfo | None:
        raise NotImplementedError(self._msg)

    def create_for_phone(self, phone: str) -> AuthCustomerInfo:
        raise NotImplementedError(self._msg)

    def create_for_email(self, email: str) -> AuthCustomerInfo:
        raise NotImplementedError(self._msg)
