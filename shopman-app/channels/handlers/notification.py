"""
Notification handler — processa directives notification.send.

Inline de shopman.notifications.handlers.
"""

from __future__ import annotations

import logging

from shopman.ordering.models import Directive

from channels.notifications import notify
from channels.topics import NOTIFICATION_SEND

logger = logging.getLogger(__name__)

# Default routing per channel when notification_routing is not configured
DEFAULT_ROUTING: dict[str, dict] = {
    "whatsapp": {"backend": "manychat", "fallback": "sms"},
    "web": {"backend": "email", "fallback": "sms"},
    "balcao": {"backend": "none"},
    "ifood": {"backend": "none"},
}


class NotificationSendHandler:
    """Processa directives de notificação. Topic: notification.send"""

    topic = NOTIFICATION_SEND

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Order

        payload = message.payload
        order_ref = payload.get("order_ref")
        template = payload.get("template", "generic")

        if not order_ref:
            message.status = "failed"
            message.last_error = "missing order_ref"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        try:
            order = Order.objects.select_related("channel").get(ref=order_ref)
        except Order.DoesNotExist:
            message.status = "failed"
            message.last_error = f"Order not found: {order_ref}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        # Skip payment reminders if already paid
        if template == "payment.reminder":
            payment_status = order.data.get("payment", {}).get("status", "")
            if payment_status in ("paid", "captured", "succeeded") or order.status not in ("new", "created"):
                message.status = "done"
                message.save(update_fields=["status", "updated_at"])
                return

        routing = self._resolve_routing(order)
        backend_name = routing.get("backend")

        if backend_name == "none" or not backend_name:
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        recipient = self._resolve_recipient(order)

        if not recipient:
            message.status = "failed"
            message.last_error = "No recipient found"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        context = {
            "order_ref": order_ref,
            "template": template,
            "order_status": order.status,
            "total_q": order.total_q,
            "items": order.data.get("items", []),
            "reason": payload.get("reason"),
        }

        payment = order.data.get("payment")
        if payment:
            context["payment"] = payment

        if backend_name == "manychat" and order.handle_type == "manychat":
            context["subscriber_id"] = order.handle_ref

        result = notify(event=template, recipient=recipient, context=context, backend=backend_name)

        if result.success:
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
        else:
            fallback = routing.get("fallback")
            if fallback and fallback != "none" and fallback != backend_name:
                fallback_result = notify(event=template, recipient=recipient, context=context, backend=fallback)
                if fallback_result.success:
                    message.status = "done"
                    message.save(update_fields=["status", "updated_at"])
                    return

            message.last_error = (result.error or "unknown")[:500]
            message.status = "failed" if message.attempts >= 5 else "queued"
            message.save(update_fields=["status", "last_error", "updated_at"])

    def _resolve_routing(self, order) -> dict:
        config = order.channel.config or {}
        channel_ref = order.channel.ref

        routing = config.get("notification_routing")
        if routing:
            return routing

        notifications = config.get("notifications", {})
        if notifications.get("backend"):
            return {"backend": notifications["backend"]}

        return DEFAULT_ROUTING.get(channel_ref, {})

    def _resolve_recipient(self, order) -> str | None:
        if order.handle_type == "manychat" and order.handle_ref:
            return order.handle_ref

        return (
            order.data.get("customer", {}).get("phone")
            or order.data.get("customer_phone")
            or (order.handle_ref if order.handle_type in ("customer", "phone") else None)
        )


__all__ = ["NotificationSendHandler", "DEFAULT_ROUTING"]
