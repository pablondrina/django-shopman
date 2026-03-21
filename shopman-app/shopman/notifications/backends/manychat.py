"""
Manychat Backend — Envia notificacoes via Manychat API.

Cobre WhatsApp, Instagram DM, Facebook Messenger e TikTok DM,
todos gerenciados pela plataforma Manychat.

Modos de envio:
1. sendFlow (preferido): Dispara Flow pre-configurado com variaveis.
2. sendContent (fallback): Envia mensagem dinamica de texto.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from shopman.notifications.protocols import NotificationResult

logger = logging.getLogger(__name__)


@dataclass
class ManychatConfig:
    """Configuracao do Manychat."""

    api_token: str
    base_url: str = "https://api.manychat.com/fb"
    default_channel: str = "whatsapp"
    flow_map: dict[str, str] = field(default_factory=dict)
    timeout: int = 15


class ManychatBackend:
    """
    NotificationBackend para Manychat.

    Envia mensagens via Manychat API, cobrindo WhatsApp,
    Instagram DM, Facebook Messenger e TikTok DM.

    Modos de envio:
    1. sendFlow (preferido): Dispara Flow pre-configurado com variaveis.
       Usado quando o evento tem flow_ns mapeado em config.flow_map.
    2. sendContent (fallback): Envia mensagem dinamica simples.
       Usado quando nao ha Flow mapeado para o evento.

    Resolucao de subscriber:
    O ``recipient`` pode ser:
    - Manychat subscriber_id (numerico)
    - Phone E.164 (+5543...)  -> resolvido via ManychatSubscriberResolver
    - Customer code (MC-XXXXXXXX) -> resolvido via ManychatSubscriberResolver
    - Email -> resolvido via ManychatSubscriberResolver

    Args:
        config: ManychatConfig com token, URLs e flow_map.
        resolver: Callable que recebe recipient (str) e retorna subscriber_id (int | None).
                  Se None, apenas recipient numerico e aceito.

    Example:
        config = ManychatConfig(
            api_token="xxx",
            flow_map={"order.confirmed": "content20240315_order_confirmed"},
        )
        backend = ManychatBackend(config=config, resolver=ManychatSubscriberResolver.resolve)
    """

    MESSAGE_TEMPLATES: dict[str, str] = {
        "order.confirmed": "Ola{customer_name_greeting}! Seu pedido {order_ref} foi confirmado. Total: {total}. Obrigado pela preferencia! \U0001f950",
        "order.ready": "Ola{customer_name_greeting}! Seu pedido {order_ref} esta pronto! \U0001f389",
        "order.dispatched": "Seu pedido {order_ref} saiu para entrega! \U0001f697",
        "order.delivered": "Pedido {order_ref} entregue. Obrigado! \u2b50",
        "order.cancelled": "Seu pedido {order_ref} foi cancelado. Qualquer duvida, estamos aqui.",
        "payment.reminder": "Ola{customer_name_greeting}! Seu pedido {order_ref} aguarda pagamento PIX. Use o codigo: {copy_paste}",
        "payment_expired": "Seu pedido {order_ref} foi cancelado pois o pagamento PIX nao foi confirmado a tempo.",
    }

    def __init__(
        self,
        config: ManychatConfig,
        resolver: Any | None = None,
    ):
        self.config = config
        self._resolver = resolver

    def send(
        self,
        *,
        event: str,
        recipient: str,
        context: dict[str, Any],
    ) -> NotificationResult:
        """
        Envia notificacao via Manychat.

        1. Resolve subscriber_id a partir do recipient.
        2. Se evento tem Flow mapeado -> sendFlow com flow_token.
        3. Senao -> sendContent com mensagem de texto.
        """
        subscriber_id = self._resolve_subscriber(recipient)
        if subscriber_id is None:
            logger.warning(f"Manychat subscriber not found: {recipient[:20]}")
            return NotificationResult(
                success=False,
                error=f"Subscriber not found for: {recipient}",
            )

        flow_ns = self.config.flow_map.get(event)
        if flow_ns:
            return self._send_flow(subscriber_id, flow_ns, context)

        message = self._build_message(event, context)
        return self._send_content(subscriber_id, message)

    def _resolve_subscriber(self, recipient: str) -> int | None:
        """
        Resolve recipient para Manychat subscriber_id.

        Estrategia:
        1. Se e numerico -> subscriber_id direto.
        2. Se resolver configurado -> delega resolucao.
        3. Senao -> None.
        """
        if recipient.isdigit():
            return int(recipient)

        if self._resolver is not None:
            return self._resolver(recipient)

        return None

    def _send_flow(
        self,
        subscriber_id: int,
        flow_ns: str,
        context: dict[str, Any],
    ) -> NotificationResult:
        """Envia Flow via Manychat API."""
        payload = {
            "subscriber_id": subscriber_id,
            "flow_ns": flow_ns,
            "flow_token": context,
        }
        return self._api_call("/sending/sendFlow", payload)

    def _send_content(
        self,
        subscriber_id: int,
        message: str,
    ) -> NotificationResult:
        """Envia mensagem de texto via Manychat API."""
        payload = {
            "subscriber_id": subscriber_id,
            "data": {
                "version": "v2",
                "content": {
                    "messages": [
                        {"type": "text", "text": message},
                    ],
                },
            },
        }
        return self._api_call("/sending/sendContent", payload)

    def _api_call(self, endpoint: str, payload: dict) -> NotificationResult:
        """Chamada HTTP para Manychat API."""
        url = f"{self.config.base_url}{endpoint}"
        data = json.dumps(payload).encode("utf-8")

        request = Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_token}",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.config.timeout) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
                status = resp_data.get("status", "")

                if status == "success":
                    logger.info(
                        f"Manychat sent: {endpoint} -> subscriber {payload.get('subscriber_id')}"
                    )
                    return NotificationResult(
                        success=True,
                        message_id=f"mc_{payload.get('subscriber_id')}",
                    )

                # API returned non-success status
                error_msg = resp_data.get("message", f"Manychat status: {status}")
                logger.warning(f"Manychat non-success: {error_msg}")
                return NotificationResult(
                    success=False,
                    error=error_msg,
                )

        except HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            logger.error(f"Manychat HTTP error: {e.code} - {error_body[:200]}")
            return NotificationResult(
                success=False,
                error=f"HTTP {e.code}: {error_body[:200]}",
            )

        except URLError as e:
            logger.error(f"Manychat URL error: {e.reason}")
            return NotificationResult(
                success=False,
                error=f"URL error: {e.reason}",
            )

        except Exception as e:
            logger.exception("Manychat error")
            return NotificationResult(
                success=False,
                error=str(e),
            )

    def _build_message(self, event: str, context: dict[str, Any]) -> str:
        """Monta mensagem de texto a partir do evento e contexto."""
        ctx = dict(context)
        if ctx.get("customer_name"):
            ctx["customer_name_greeting"] = f", {ctx['customer_name']}"
        else:
            ctx["customer_name_greeting"] = ""

        template = self.MESSAGE_TEMPLATES.get(event)
        if template:
            try:
                return template.format(**ctx)
            except KeyError:
                pass

        # Fallback generico
        order_ref = context.get("order_ref", "")
        if order_ref:
            return f"Notificacao: {event} — Pedido {order_ref}"
        return f"Notificacao: {event}"
