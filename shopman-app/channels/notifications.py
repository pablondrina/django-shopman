"""
Channels notification service — registry + dispatch.

Migrado de shopman.notifications.service.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

from channels.protocols import NotificationBackend, NotificationResult

logger = logging.getLogger(__name__)

# Registry de backends
_backends: dict[str, NotificationBackend] = {}


def register_backend(name: str, backend: NotificationBackend) -> None:
    _backends[name] = backend
    logger.debug("Notification backend registered: %s", name)


def get_backend(name: str | None = None) -> NotificationBackend | None:
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
    backend_instance = get_backend(backend)

    if not backend_instance:
        backend_name = backend or "default"
        logger.warning("Notification backend not found: %s", backend_name)
        return NotificationResult(success=False, error=f"Backend not found: {backend_name}")

    try:
        result = backend_instance.send(event=event, recipient=recipient, context=context)
        if result.success:
            logger.info("Notification sent: %s -> %s...", event, recipient[:20])
        else:
            logger.warning("Notification failed: %s -> %s", event, result.error)
        return result
    except Exception as e:
        logger.exception("Notification error: %s", event)
        return NotificationResult(success=False, error=str(e))
