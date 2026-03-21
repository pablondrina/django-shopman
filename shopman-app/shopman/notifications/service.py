"""
Shopman Notifications Service — Servico central (simples).
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

from .protocols import NotificationBackend, NotificationResult

logger = logging.getLogger(__name__)

# Registry de backends
_backends: dict[str, NotificationBackend] = {}


def register_backend(name: str, backend: NotificationBackend) -> None:
    """
    Registra um backend de notificacao.

    Args:
        name: Nome do backend (ex: "whatsapp", "sms")
        backend: Instancia do backend
    """
    _backends[name] = backend
    logger.debug(f"Notification backend registered: {name}")


def get_backend(name: str | None = None) -> NotificationBackend | None:
    """
    Retorna backend por nome ou o default.

    Args:
        name: Nome do backend (None = usa default das settings)

    Returns:
        Backend ou None se nao encontrado
    """
    if name is None:
        config = getattr(settings, "SHOPMAN_NOTIFICATIONS", {})
        name = config.get("default_backend", "console")

    return _backends.get(name)


def notify(
    *,
    event: str,
    recipient: str,
    context: dict[str, Any],
    backend: str | None = None,
) -> NotificationResult:
    """
    Envia notificacao.

    Args:
        event: Tipo do evento (ex: "order.confirmed")
        recipient: Destinatario
        context: Dados para a mensagem
        backend: Nome do backend (None = usa default)

    Returns:
        NotificationResult

    Example:
        notify(
            event="order.confirmed",
            recipient="+5511999999999",
            context={"order_ref": "ORD-123"},
            backend="whatsapp",
        )
    """
    backend_instance = get_backend(backend)

    if not backend_instance:
        backend_name = backend or "default"
        logger.warning(f"Notification backend not found: {backend_name}")
        return NotificationResult(
            success=False,
            error=f"Backend not found: {backend_name}",
        )

    try:
        result = backend_instance.send(
            event=event,
            recipient=recipient,
            context=context,
        )
        if result.success:
            logger.info(f"Notification sent: {event} -> {recipient[:20]}...")
        else:
            logger.warning(f"Notification failed: {event} -> {result.error}")
        return result

    except Exception as e:
        logger.exception(f"Notification error: {event}")
        return NotificationResult(
            success=False,
            error=str(e),
        )
