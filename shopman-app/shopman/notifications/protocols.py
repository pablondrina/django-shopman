"""
Shopman Notifications Protocols — Interface para backends.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class NotificationResult:
    """Resultado do envio."""

    success: bool
    message_id: str | None = None
    error: str | None = None


@runtime_checkable
class NotificationBackend(Protocol):
    """
    Protocol para backends de notificacao.

    Implemente este protocol para criar backends customizados
    (WhatsApp, Telegram, SMS, Push, etc).
    """

    def send(
        self,
        *,
        event: str,
        recipient: str,
        context: dict[str, Any],
    ) -> NotificationResult:
        """
        Envia notificacao.

        Args:
            event: Tipo do evento (ex: "order.confirmed")
            recipient: Destinatario (email, telefone, URL, etc)
            context: Dados para a mensagem

        Returns:
            NotificationResult com status
        """
        ...
