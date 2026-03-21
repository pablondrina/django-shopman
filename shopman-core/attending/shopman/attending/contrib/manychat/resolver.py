"""
Manychat Subscriber Resolver — Resolve recipient → subscriber_id.

Usado pelo ManychatBackend (ordering) para converter phone/email/ref
em Manychat subscriber_id para envio de mensagens outbound.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shopman.attending.models import Customer

logger = logging.getLogger(__name__)


class ManychatSubscriberResolver:
    """
    Resolve recipient → Manychat subscriber_id.

    Usa CustomerIdentifier (contrib/identifiers) para mapear
    phone/email/ref → MANYCHAT subscriber_id.

    Ordem de tentativa:
    1. Numérico direto → subscriber_id
    2. Phone E.164 (+55...) → CustomerIdentifier(PHONE) → Customer
       → CustomerIdentifier(MANYCHAT) → subscriber_id
    3. Customer code (MC-...) → Customer → CustomerIdentifier(MANYCHAT)
    4. Email → CustomerIdentifier(EMAIL) → MANYCHAT
    """

    @classmethod
    def resolve(cls, recipient: str) -> int | None:
        """
        Resolve subscriber_id a partir do recipient.

        Args:
            recipient: subscriber_id numérico, phone E.164, customer code ou email.

        Returns:
            Manychat subscriber_id (int) ou None se não encontrado.
        """
        if recipient.isdigit():
            return int(recipient)

        customer = cls._find_customer(recipient)
        if not customer:
            logger.debug(f"Manychat resolver: customer not found for {recipient[:20]}")
            return None

        subscriber_id = cls._get_manychat_id(customer)
        if subscriber_id is None:
            logger.debug(
                f"Manychat resolver: no MANYCHAT identifier for customer {customer.ref}"
            )
        return subscriber_id

    @classmethod
    def _find_customer(cls, recipient: str) -> Customer | None:
        """Busca customer por phone, code ou email."""
        from shopman.attending.contrib.identifiers.models import (
            CustomerIdentifier,
            IdentifierType,
        )
        from shopman.attending.models import Customer

        if recipient.startswith("+"):
            # Phone → busca por identifier
            try:
                ident = CustomerIdentifier.objects.select_related("customer").get(
                    identifier_type=IdentifierType.PHONE,
                    identifier_value=recipient,
                    customer__is_active=True,
                )
                return ident.customer
            except CustomerIdentifier.DoesNotExist:
                return None

        if recipient.startswith("MC-"):
            # Customer code
            return Customer.objects.filter(
                ref=recipient, is_active=True
            ).first()

        if "@" in recipient:
            # Email
            try:
                ident = CustomerIdentifier.objects.select_related("customer").get(
                    identifier_type=IdentifierType.EMAIL,
                    identifier_value=recipient.lower().strip(),
                    customer__is_active=True,
                )
                return ident.customer
            except CustomerIdentifier.DoesNotExist:
                return None

        return None

    @classmethod
    def _get_manychat_id(cls, customer: Customer) -> int | None:
        """Busca Manychat subscriber_id do customer."""
        from shopman.attending.contrib.identifiers.models import (
            CustomerIdentifier,
            IdentifierType,
        )

        try:
            ident = CustomerIdentifier.objects.get(
                customer=customer,
                identifier_type=IdentifierType.MANYCHAT,
            )
            return int(ident.identifier_value)
        except (CustomerIdentifier.DoesNotExist, ValueError):
            return None
