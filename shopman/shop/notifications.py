"""
Notification dispatch — registry + send.

Adapters are function-style modules in shopman.adapters.notification_*.
Each adapter exposes:
    send(recipient, template, context, **config) -> bool
    is_available(recipient, **config) -> bool

The registry maps backend names to adapter modules. Registration happens in
setup.py at startup. Callers use notify() to dispatch.
"""

from __future__ import annotations

import importlib
import logging
from types import ModuleType
from typing import Any

logger = logging.getLogger(__name__)

from shopman.shop.protocols import NotificationResult

# Registry: backend name → adapter module (with a `send` function)
_adapters: dict[str, ModuleType] = {}


def register_backend(name: str, adapter: ModuleType) -> None:
    """Register a notification adapter module under `name`."""
    _adapters[name] = adapter
    logger.debug("Notification backend registered: %s", name)


def get_backend(name: str | None = None) -> ModuleType | None:
    """Resolve adapter module by name. Falls back to 'console' when name is None."""
    if name is None:
        name = "console"
    return _adapters.get(name)


def notify(
    *,
    event: str,
    recipient: str,
    context: dict[str, Any],
    backend: str | None = None,
) -> NotificationResult:
    """Dispatch a notification through the named adapter.

    Args:
        event: Template/event name (e.g. "order_confirmed").
        recipient: Recipient identifier (phone, email, subscriber_id).
        context: Template variables passed to the adapter.
        backend: Backend name ("console", "email", "manychat", "sms").

    Returns:
        NotificationResult with success/error fields.
    """
    adapter = get_backend(backend)

    if not adapter:
        backend_name = backend or "default"
        logger.warning("Notification backend not found: %s", backend_name)
        return NotificationResult(success=False, error=f"Backend not found: {backend_name}")

    try:
        success = adapter.send(recipient=recipient, template=event, context=context)
        if success:
            logger.info("Notification sent: %s -> %s...", event, recipient[:20])
            return NotificationResult(success=True, message_id=f"{backend}_{recipient[:20]}")
        else:
            error_msg = f"Adapter {backend} returned False"
            logger.warning("Notification failed: %s -> %s", event, error_msg)
            return NotificationResult(success=False, error=error_msg)
    except Exception as e:
        logger.exception("Notification error: %s", event)
        return NotificationResult(success=False, error=str(e))
