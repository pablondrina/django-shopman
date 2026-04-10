"""
Notification service.

Adapter: get_adapter("notification", channel=...) → notification_manychat / email / console

ASYNC — creates Directive for later processing. The actual send + fallback
chain is handled by the Directive handler, not this service.
"""

from __future__ import annotations

import logging

from shopman.orderman.models import Directive

logger = logging.getLogger(__name__)

TOPIC = "notification.send"


def send(order, template: str) -> None:
    """
    Schedule a notification for the order.

    Creates a Directive with topic="notification.send". The handler that
    processes the Directive resolves the adapter, builds context, and
    executes the fallback chain (manychat → email → console).

    ASYNC — does not block the request.
    """
    payload = {
        "order_ref": order.ref,
        "channel_ref": order.channel_ref or "",
        "template": template,
    }

    # Include origin_channel for routing
    origin = (order.data or {}).get("origin_channel")
    if origin:
        payload["origin_channel"] = origin

    Directive.objects.create(topic=TOPIC, payload=payload)

    logger.info("notification.send: queued %s for order %s", template, order.ref)
