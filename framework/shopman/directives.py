"""
Directive queue helper — single entry point for async work.

Instead of Directive.objects.create() scattered across services,
use directives.queue() for consistent payload structure.
"""

from shopman.omniman.models import Directive


def queue(topic, order, **extra):
    """
    Create a Directive for async processing.

    Always includes order_ref and channel_ref. Extra kwargs are
    merged into the payload.

    Usage:
        from shopman import directives
        directives.queue("notification.send", order, template="order_confirmed")
    """
    payload = {"order_ref": order.ref}
    if order.channel:
        payload["channel_ref"] = order.channel.ref
    payload.update(extra)
    return Directive.objects.create(topic=topic, payload=payload)
