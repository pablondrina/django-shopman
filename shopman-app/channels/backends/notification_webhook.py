"""
Webhook Backend — HTTP POST universal.

Este e o backend mais importante: conecta com qualquer servico externo
(Zapier, n8n, Make, seu proprio servidor, etc).

A partir do webhook voce pode rotear para WhatsApp, SMS, Telegram, etc.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from channels.protocols import NotificationResult

logger = logging.getLogger(__name__)


class WebhookBackend:
    """
    Backend que envia notificacoes via HTTP POST.

    Conecta com qualquer servico externo:
    - Zapier, n8n, Make (automacao)
    - Seu proprio microservico
    - APIs de WhatsApp, SMS, etc

    Args:
        url: URL do webhook
        headers: Headers adicionais (ex: Authorization)
        timeout: Timeout em segundos (default: 10)

    Example:
        backend = WebhookBackend(
            url="https://hooks.zapier.com/hooks/catch/xxx",
            headers={"X-Api-Key": "secret"},
        )
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: int = 10,
    ):
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout

    def send(
        self,
        *,
        event: str,
        recipient: str,
        context: dict[str, Any],
    ) -> NotificationResult:
        """Envia notificacao via HTTP POST."""
        payload = {
            "event": event,
            "recipient": recipient,
            **context,
        }

        try:
            request = Request(
                self.url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    **self.headers,
                },
                method="POST",
            )

            with urlopen(request, timeout=self.timeout) as response:
                logger.debug(f"Webhook sent: {event} -> {self.url} (status={response.status})")
                return NotificationResult(
                    success=True,
                    message_id=f"webhook_{response.status}",
                )

        except HTTPError as e:
            logger.error(f"Webhook HTTP error: {e.code} {e.reason}")
            return NotificationResult(
                success=False,
                error=f"HTTP {e.code}: {e.reason}",
            )

        except URLError as e:
            logger.error(f"Webhook URL error: {e.reason}")
            return NotificationResult(
                success=False,
                error=str(e.reason),
            )

        except Exception as e:
            logger.exception("Webhook unexpected error")
            return NotificationResult(
                success=False,
                error=str(e),
            )
