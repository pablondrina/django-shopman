"""
WhatsApp Backend — Template para integracao com WhatsApp.

Este e um TEMPLATE. Voce deve configurar com seu provider:
- Meta Cloud API (oficial)
- Twilio
- MessageBird
- Vonage
- etc.

O exemplo abaixo usa a Meta Cloud API.
Adapte para seu provider especifico.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from channels.protocols import NotificationResult

logger = logging.getLogger(__name__)


class WhatsAppBackend:
    """
    Backend para WhatsApp via Meta Cloud API.

    Args:
        phone_number_id: ID do numero no Meta Business
        access_token: Token de acesso da API
        api_version: Versao da API (default: v17.0)

    Example:
        backend = WhatsAppBackend(
            phone_number_id="1234567890",
            access_token="EAAxxxxx",
        )

    Configuracao via settings:
        SHOPMAN_NOTIFICATIONS = {
            "backends": {
                "whatsapp": {
                    "class": "channels.backends.notification_whatsapp.WhatsAppBackend",
                    "phone_number_id": "1234567890",
                    "access_token": os.environ["WHATSAPP_TOKEN"],
                },
            },
        }

    Templates de mensagem devem ser aprovados no Meta Business Manager.
    """

    API_URL = "https://graph.facebook.com/{version}/{phone_id}/messages"

    def __init__(
        self,
        phone_number_id: str,
        access_token: str,
        api_version: str = "v17.0",
    ):
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.api_version = api_version
        self.url = self.API_URL.format(
            version=api_version,
            phone_id=phone_number_id,
        )

    def send(
        self,
        *,
        event: str,
        recipient: str,  # Numero no formato +5511999999999
        context: dict[str, Any],
    ) -> NotificationResult:
        """
        Envia mensagem via WhatsApp.

        O 'event' e mapeado para um template aprovado no Meta.
        """
        # Mapeia evento para template do WhatsApp
        template_name = self._get_template_name(event)

        # Monta payload da Meta Cloud API
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient.replace("+", "").replace("-", "").replace(" ", ""),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": context.get("language", "pt_BR")},
                "components": self._build_components(context),
            },
        }

        try:
            request = Request(
                self.url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.access_token}",
                },
                method="POST",
            )

            with urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
                message_id = data.get("messages", [{}])[0].get("id", "")
                logger.info(f"WhatsApp sent: {event} -> {recipient} (id={message_id})")
                return NotificationResult(
                    success=True,
                    message_id=message_id,
                )

        except HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            logger.error(f"WhatsApp HTTP error: {e.code} - {error_body}")
            return NotificationResult(
                success=False,
                error=f"HTTP {e.code}: {error_body[:200]}",
            )

        except Exception as e:
            logger.exception("WhatsApp error")
            return NotificationResult(
                success=False,
                error=str(e),
            )

    def _get_template_name(self, event: str) -> str:
        """
        Mapeia evento para nome do template no Meta.

        Override este metodo para customizar o mapeamento.
        """
        # Converte "order.confirmed" -> "order_confirmed"
        return event.replace(".", "_")

    def _build_components(self, context: dict[str, Any]) -> list[dict]:
        """
        Monta componentes do template.

        Override este metodo para customizar os parametros.
        """
        # Extrai variaveis comuns
        params = []
        for key in ["order_ref", "customer_name", "total", "status"]:
            if key in context:
                params.append({"type": "text", "text": str(context[key])})

        if not params:
            return []

        return [
            {
                "type": "body",
                "parameters": params,
            }
        ]
