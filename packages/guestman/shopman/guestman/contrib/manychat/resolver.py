"""
Manychat Subscriber Resolver — Resolve recipient → subscriber_id.

Usado pelo ManychatBackend (orderman) para converter phone/email/ref
em Manychat subscriber_id para envio de mensagens outbound.

Estratégia de resolução (em ordem):
1. Numérico direto → subscriber_id
2. DB: CustomerIdentifier(MANYCHAT) via phone/email/ref
3. API fallback: GET /fb/subscriber/findBySystemField (phone)
   → persiste como CustomerIdentifier para próximas chamadas
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from shopman.guestman.models import Customer

logger = logging.getLogger(__name__)

# ManyChat API base URL
_API_BASE = "https://api.manychat.com/fb"
_API_TIMEOUT = 10


class ManychatSubscriberResolver:
    """
    Resolve recipient → Manychat subscriber_id.

    Usa CustomerIdentifier (contrib/identifiers) para mapear
    phone/email/ref → MANYCHAT subscriber_id.

    Se não encontrar no banco, consulta a API do ManyChat via
    findBySystemField (phone) e persiste o resultado.
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

        # Fast path: customer exists and has MANYCHAT identifier
        if customer:
            subscriber_id = cls._get_manychat_id(customer)
            if subscriber_id is not None:
                return subscriber_id

        # API fallback: lookup subscriber by phone via ManyChat API
        if recipient.startswith("+"):
            subscriber_id = cls._lookup_by_phone_api(recipient)
            if subscriber_id is not None and customer:
                cls._persist_manychat_id(customer, subscriber_id)
            return subscriber_id

        if not customer:
            logger.debug("Manychat resolver: customer not found for %s", recipient[:20])
        return None

    @classmethod
    def _find_customer(cls, recipient: str) -> Customer | None:
        """Busca customer por phone, code ou email."""
        from shopman.guestman.contrib.identifiers.models import (
            CustomerIdentifier,
            IdentifierType,
        )
        from shopman.guestman.models import Customer

        if recipient.startswith("+"):
            try:
                ident = CustomerIdentifier.objects.select_related("customer").get(
                    identifier_type=IdentifierType.PHONE,
                    identifier_value=recipient,
                    customer__is_active=True,
                )
                return ident.customer
            except CustomerIdentifier.DoesNotExist:
                # Also try direct phone field on Customer
                return Customer.objects.filter(
                    phone=recipient, is_active=True,
                ).first()

        if recipient.startswith("MC-"):
            return Customer.objects.filter(
                ref=recipient, is_active=True,
            ).first()

        if "@" in recipient:
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
        from shopman.guestman.contrib.identifiers.models import (
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

    @classmethod
    def _lookup_by_phone_api(cls, phone: str) -> int | None:
        """Consulta ManyChat API para encontrar subscriber por telefone.

        GET /fb/subscriber/findBySystemField?field=whatsapp_phone&value=<phone>
        """
        from django.conf import settings

        api_token = getattr(settings, "MANYCHAT_API_TOKEN", "")
        if not api_token:
            return None

        # ManyChat expects phone without + prefix for WhatsApp lookup
        phone_value = phone.lstrip("+")

        url = (
            f"{_API_BASE}/subscriber/findBySystemField"
            f"?field=whatsapp_phone&value={phone_value}"
        )
        request = Request(url, headers={
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
        })

        try:
            with urlopen(request, timeout=_API_TIMEOUT) as response:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("status") == "success":
                    subscriber = data.get("data", {})
                    subscriber_id = subscriber.get("id")
                    if subscriber_id:
                        logger.info(
                            "Manychat resolver: found subscriber %s for phone %s via API",
                            subscriber_id, phone[:8],
                        )
                        return int(subscriber_id)
        except HTTPError as e:
            if e.code == 404:
                logger.debug("Manychat resolver: subscriber not found for phone %s", phone[:8])
            else:
                logger.warning("Manychat resolver: API error %d for phone %s", e.code, phone[:8])
        except (URLError, ValueError, Exception):
            logger.debug("Manychat resolver: API call failed for phone %s", phone[:8], exc_info=True)

        return None

    @classmethod
    def _persist_manychat_id(cls, customer: Customer, subscriber_id: int) -> None:
        """Persiste o subscriber_id como CustomerIdentifier para evitar future API calls."""
        from shopman.guestman.contrib.identifiers.models import (
            CustomerIdentifier,
            IdentifierType,
        )

        CustomerIdentifier.objects.get_or_create(
            customer=customer,
            identifier_type=IdentifierType.MANYCHAT,
            defaults={
                "identifier_value": str(subscriber_id),
                "is_primary": True,
                "source_system": "manychat_api_lookup",
            },
        )
