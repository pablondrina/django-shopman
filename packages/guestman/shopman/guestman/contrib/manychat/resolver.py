"""
Manychat Subscriber Resolver — Resolve recipient → subscriber_id.

Usado pelo ManychatBackend (orderman) para converter phone/email/ref
em Manychat subscriber_id para envio de mensagens outbound.

Estratégia de resolução (em ordem):
1. Numérico direto → subscriber_id
2. DB: CustomerIdentifier(MANYCHAT) via phone/email/ref
3. API fallback: GET /fb/subscriber/findBySystemField (phone)
4. API bootstrap: POST /fb/subscriber/createSubscriber (whatsapp_phone)
   → persiste como CustomerIdentifier para próximas chamadas quando houver customer
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from shopman.guestman.models import Customer

logger = logging.getLogger(__name__)

# ManyChat API base URL
_API_BASE = "https://api.manychat.com/fb"
_API_TIMEOUT = 10


def _read_http_error_body(error: HTTPError) -> str:
    try:
        return error.read().decode("utf-8", "replace")[:300]
    except Exception:
        return ""


def _subscriber_id(data: dict) -> int | None:
    subscriber = data.get("data") or {}
    if isinstance(subscriber, list):
        subscriber = subscriber[0] if subscriber else {}
    if not isinstance(subscriber, dict):
        return None

    subscriber_id = subscriber.get("id")
    if not subscriber_id:
        return None

    try:
        return int(subscriber_id)
    except (TypeError, ValueError):
        return None


def _manychat_failure_message(data: dict) -> str:
    message = data.get("message") or data.get("error") or data.get("status")
    if message:
        return str(message)[:300]
    return json.dumps(data, ensure_ascii=True)[:300]


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

        # API fallback: lookup subscriber by phone, then create a WhatsApp
        # contact when the phone is not yet known to ManyChat.
        if recipient.startswith("+"):
            subscriber_id = cls._lookup_by_phone_api(recipient)
            if subscriber_id is None:
                subscriber_id = cls._create_whatsapp_subscriber_api(recipient)
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

        GET /fb/subscriber/findBySystemField?phone=<E.164>
        """
        from django.conf import settings

        api_token = getattr(settings, "MANYCHAT_API_TOKEN", "")
        if not api_token:
            return None

        url = (
            f"{_API_BASE}/subscriber/findBySystemField"
            f"?{urlencode({'phone': phone})}"
        )
        request = Request(url, headers={
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
        })

        try:
            with urlopen(request, timeout=_API_TIMEOUT) as response:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("status") == "success":
                    subscriber_id = _subscriber_id(data)
                    if subscriber_id:
                        logger.info(
                            "Manychat resolver: found subscriber %s for phone %s via API",
                            subscriber_id, phone[:8],
                        )
                        return subscriber_id
                    logger.info(
                        "Manychat resolver: no subscriber found for phone %s via system field",
                        phone[:8],
                    )
                else:
                    logger.warning(
                        "Manychat resolver: lookup failed for phone %s: %s",
                        phone[:8],
                        _manychat_failure_message(data),
                    )
        except HTTPError as e:
            error_body = _read_http_error_body(e)
            if e.code == 404:
                logger.debug("Manychat resolver: subscriber not found for phone %s", phone[:8])
            else:
                logger.warning(
                    "Manychat resolver: API error %d for phone %s: %s",
                    e.code,
                    phone[:8],
                    error_body,
                )
        except (URLError, ValueError, Exception):
            logger.debug("Manychat resolver: API call failed for phone %s", phone[:8], exc_info=True)

        return None

    @classmethod
    def _create_whatsapp_subscriber_api(cls, phone: str) -> int | None:
        """Cria contato WhatsApp no ManyChat e retorna subscriber_id.

        POST /fb/subscriber/createSubscriber
        """
        from django.conf import settings

        api_token = getattr(settings, "MANYCHAT_API_TOKEN", "")
        if not api_token:
            return None

        payload = {
            "whatsapp_phone": phone,
            "phone": phone,
            "has_opt_in_sms": False,
        }
        request = Request(
            f"{_API_BASE}/subscriber/createSubscriber",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=_API_TIMEOUT) as response:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("status") == "success":
                    subscriber_id = _subscriber_id(data)
                    if subscriber_id:
                        logger.info(
                            "Manychat resolver: created WhatsApp subscriber %s for phone %s",
                            subscriber_id,
                            phone[:8],
                        )
                        return subscriber_id
                    logger.warning(
                        "Manychat resolver: createSubscriber returned no id for phone %s",
                        phone[:8],
                    )
                else:
                    logger.warning(
                        "Manychat resolver: createSubscriber failed for phone %s: %s",
                        phone[:8],
                        _manychat_failure_message(data),
                    )
        except HTTPError as e:
            logger.warning(
                "Manychat resolver: createSubscriber HTTP error %d for phone %s: %s",
                e.code,
                phone[:8],
                _read_http_error_body(e),
            )
        except (URLError, ValueError, Exception):
            logger.debug(
                "Manychat resolver: createSubscriber call failed for phone %s",
                phone[:8],
                exc_info=True,
            )

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
