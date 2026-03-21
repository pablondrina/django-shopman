"""
DirectiveHandler for notification.send — dispatches notifications via pluggable backend.

Registered in orchestration.py via ``register_extensions()``.
Processed by the ordering dispatch system (at-least-once).
"""

from __future__ import annotations

import logging

from shopman.contrib.notification_backends import LogNotificationBackend, NotificationBackend

logger = logging.getLogger("shopman.contrib.notification")


class NotificationHandler:
    """
    Processes ``notification.send`` directives after commit.

    Payload (from CommitService):
        - order_ref: str
        - channel_ref: str
        - session_key: str
        - template: str
        - context: dict (optional, extra data for rendering)

    Delegates actual dispatch to the configured ``NotificationBackend``.
    Idempotent: skips if a delivery id is already recorded in
    ``result.delivery_id``.
    """

    topic = "notification.send"

    def __init__(self, backend: NotificationBackend | None = None):
        self.backend: NotificationBackend = backend or LogNotificationBackend()

    def handle(self, *, message, ctx):
        payload = message.payload
        order_ref = payload.get("order_ref", "?")
        channel_ref = payload.get("channel_ref", "?")
        template = payload.get("template", "default")

        # Idempotency: already sent
        if payload.get("result", {}).get("delivery_id"):
            logger.debug(
                "notification.send: already delivered for order %s (delivery_id=%s)",
                order_ref,
                payload["result"]["delivery_id"],
            )
            return

        context = payload.get("context", {})
        context.setdefault("session_key", payload.get("session_key", ""))

        delivery_id = self.backend.send(
            order_ref=order_ref,
            channel_ref=channel_ref,
            template=template,
            context=context,
        )

        if not payload.get("result"):
            payload["result"] = {}
        payload["result"]["delivery_id"] = delivery_id
        message.payload = payload
        message.save(update_fields=["payload"])

        logger.info(
            "notification.send: delivered order=%s channel=%s template=%s delivery_id=%s",
            order_ref,
            channel_ref,
            template,
            delivery_id,
        )
