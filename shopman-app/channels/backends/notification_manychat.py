"""
Manychat notification backend — envia via Manychat API.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from channels.protocols import NotificationResult

logger = logging.getLogger(__name__)


@dataclass
class ManychatConfig:
    """Configuração do Manychat."""

    api_token: str
    base_url: str = "https://api.manychat.com/fb"
    default_channel: str = "whatsapp"
    flow_map: dict[str, str] = field(default_factory=dict)
    timeout: int = 15


class ManychatBackend:
    """NotificationBackend para Manychat (WhatsApp, Instagram DM, etc.)."""

    MESSAGE_TEMPLATES: dict[str, str] = {
        "order.confirmed": "Ola{customer_name_greeting}! Seu pedido {order_ref} foi confirmado. Total: {total}. Obrigado pela preferencia! \U0001f950",
        "order.ready": "Ola{customer_name_greeting}! Seu pedido {order_ref} esta pronto! \U0001f389",
        "order.dispatched": "Seu pedido {order_ref} saiu para entrega! \U0001f697",
        "order.delivered": "Pedido {order_ref} entregue. Obrigado! \u2b50",
        "order.cancelled": "Seu pedido {order_ref} foi cancelado. Qualquer duvida, estamos aqui.",
        "payment.reminder": "Ola{customer_name_greeting}! Seu pedido {order_ref} aguarda pagamento PIX. Use o codigo: {copy_paste}",
        "payment_expired": "Seu pedido {order_ref} foi cancelado pois o pagamento PIX nao foi confirmado a tempo.",
    }

    def __init__(self, config: ManychatConfig, resolver: Any | None = None):
        self.config = config
        self._resolver = resolver

    def send(self, *, event: str, recipient: str, context: dict[str, Any]) -> NotificationResult:
        subscriber_id = self._resolve_subscriber(recipient)
        if subscriber_id is None:
            return NotificationResult(success=False, error=f"Subscriber not found for: {recipient}")

        flow_ns = self.config.flow_map.get(event)
        if flow_ns:
            return self._send_flow(subscriber_id, flow_ns, context)

        message = self._build_message(event, context)
        return self._send_content(subscriber_id, message)

    def _resolve_subscriber(self, recipient: str) -> int | None:
        if recipient.isdigit():
            return int(recipient)
        if self._resolver is not None:
            return self._resolver(recipient)
        return None

    def _send_flow(self, subscriber_id: int, flow_ns: str, context: dict[str, Any]) -> NotificationResult:
        payload = {"subscriber_id": subscriber_id, "flow_ns": flow_ns, "flow_token": context}
        return self._api_call("/sending/sendFlow", payload)

    def _send_content(self, subscriber_id: int, message: str) -> NotificationResult:
        payload = {
            "subscriber_id": subscriber_id,
            "data": {"version": "v2", "content": {"messages": [{"type": "text", "text": message}]}},
        }
        return self._api_call("/sending/sendContent", payload)

    def _api_call(self, endpoint: str, payload: dict) -> NotificationResult:
        url = f"{self.config.base_url}{endpoint}"
        data = json.dumps(payload).encode("utf-8")
        request = Request(url, data=data, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_token}",
        }, method="POST")

        try:
            with urlopen(request, timeout=self.config.timeout) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
                if resp_data.get("status") == "success":
                    return NotificationResult(success=True, message_id=f"mc_{payload.get('subscriber_id')}")
                return NotificationResult(success=False, error=resp_data.get("message", "Manychat error"))
        except HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            return NotificationResult(success=False, error=f"HTTP {e.code}: {error_body[:200]}")
        except URLError as e:
            return NotificationResult(success=False, error=f"URL error: {e.reason}")
        except Exception as e:
            return NotificationResult(success=False, error=str(e))

    def _build_message(self, event: str, context: dict[str, Any]) -> str:
        ctx = dict(context)
        ctx["customer_name_greeting"] = f", {ctx['customer_name']}" if ctx.get("customer_name") else ""

        template = self.MESSAGE_TEMPLATES.get(event)
        if template:
            try:
                return template.format(**ctx)
            except KeyError:
                pass

        order_ref = context.get("order_ref", "")
        return f"Notificacao: {event} — Pedido {order_ref}" if order_ref else f"Notificacao: {event}"


__all__ = ["ManychatBackend", "ManychatConfig"]
