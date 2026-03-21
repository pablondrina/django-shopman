"""
SMS Backend — Template para integracao com SMS.

Este e um TEMPLATE. Voce deve configurar com seu provider:
- Twilio
- AWS SNS
- Vonage (Nexmo)
- MessageBird
- Zenvia (Brasil)
- etc.

O exemplo abaixo usa Twilio.
Adapte para seu provider especifico.
"""

from __future__ import annotations

import json
import logging
from base64 import b64encode
from typing import Any
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import URLError, HTTPError

from shopman.notifications.protocols import NotificationResult

logger = logging.getLogger(__name__)


class TwilioSMSBackend:
    """
    Backend para SMS via Twilio.

    Args:
        account_sid: Twilio Account SID
        auth_token: Twilio Auth Token
        from_number: Numero de origem (formato E.164: +15551234567)

    Example:
        backend = TwilioSMSBackend(
            account_sid="ACxxxxx",
            auth_token="xxxxx",
            from_number="+15551234567",
        )

    Configuracao via settings:
        SHOPMAN_NOTIFICATIONS = {
            "backends": {
                "sms": {
                    "class": "shopman.notifications.backends.TwilioSMSBackend",
                    "account_sid": os.environ["TWILIO_SID"],
                    "auth_token": os.environ["TWILIO_TOKEN"],
                    "from_number": "+15551234567",
                },
            },
        }
    """

    API_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

    # Templates de mensagem por evento
    MESSAGE_TEMPLATES = {
        "order.confirmed": "Pedido {order_ref} confirmado! Total: {total}",
        "order.ready": "Pedido {order_ref} pronto para retirada!",
        "order.dispatched": "Pedido {order_ref} saiu para entrega!",
        "order.delivered": "Pedido {order_ref} entregue. Obrigado!",
    }

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
    ):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.url = self.API_URL.format(sid=account_sid)

    def send(
        self,
        *,
        event: str,
        recipient: str,  # Numero no formato +5511999999999
        context: dict[str, Any],
    ) -> NotificationResult:
        """Envia SMS via Twilio."""
        # Monta mensagem
        message = self._build_message(event, context)

        # Monta payload (form-urlencoded para Twilio)
        payload = urlencode({
            "To": recipient,
            "From": self.from_number,
            "Body": message,
        }).encode("utf-8")

        # Auth Basic
        credentials = b64encode(
            f"{self.account_sid}:{self.auth_token}".encode()
        ).decode("ascii")

        try:
            request = Request(
                self.url,
                data=payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": f"Basic {credentials}",
                },
                method="POST",
            )

            with urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
                message_sid = data.get("sid", "")
                logger.info(f"SMS sent: {event} -> {recipient} (sid={message_sid})")
                return NotificationResult(
                    success=True,
                    message_id=message_sid,
                )

        except HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            logger.error(f"Twilio HTTP error: {e.code} - {error_body}")
            return NotificationResult(
                success=False,
                error=f"HTTP {e.code}: {error_body[:200]}",
            )

        except Exception as e:
            logger.exception("SMS error")
            return NotificationResult(
                success=False,
                error=str(e),
            )

    def _build_message(self, event: str, context: dict[str, Any]) -> str:
        """
        Monta mensagem a partir do template.

        Override este metodo para customizar as mensagens.
        """
        template = self.MESSAGE_TEMPLATES.get(event)

        if template:
            try:
                return template.format(**context)
            except KeyError:
                pass

        # Fallback generico
        return f"Shopman: {event} - {context.get('order_ref', 'N/A')}"
