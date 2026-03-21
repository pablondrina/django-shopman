"""
Notification backends — pluggable dispatch for notification directives.

The ``NotificationBackend`` protocol defines the interface; concrete backends
implement ``send()``.  ``LogNotificationBackend`` is the default (logs only).
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger("shopman.contrib.notification")


@runtime_checkable
class NotificationBackend(Protocol):
    """Protocol for notification dispatch backends."""

    def send(self, *, order_ref: str, channel_ref: str, template: str, context: dict) -> str:
        """Send a notification and return a delivery id (or opaque reference).

        Parameters
        ----------
        order_ref : str
            The order reference this notification relates to.
        channel_ref : str
            The sales channel reference.
        template : str
            Template identifier (e.g. ``"order_confirmed"``).
        context : dict
            Arbitrary context data for rendering the notification.

        Returns
        -------
        str
            A delivery identifier (backend-specific).
        """
        ...


class LogNotificationBackend:
    """Default backend — logs the notification without side-effects."""

    def send(self, *, order_ref: str, channel_ref: str, template: str, context: dict) -> str:
        logger.info(
            "notification: order=%s channel=%s template=%s context=%s",
            order_ref,
            channel_ref,
            template,
            context,
        )
        return f"log:{order_ref}:{template}"
