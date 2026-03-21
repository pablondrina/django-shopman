"""
Shopman Notification Handlers — Processa directives notification.send.

Conecta o sistema de directives ao NotificationService.

Roteamento por canal de origem:
- whatsapp -> manychat
- web -> email (fallback: sms)
- balcao -> none (skip)
- ifood -> none (iFood gerencia)
"""

from __future__ import annotations

import logging

from shopman.ordering.models import Directive

from .service import notify

logger = logging.getLogger(__name__)

# Default routing per channel when notification_routing is not configured
DEFAULT_ROUTING: dict[str, dict] = {
    "whatsapp": {"backend": "manychat", "fallback": "sms"},
    "web": {"backend": "email", "fallback": "sms"},
    "balcao": {"backend": "none"},
    "ifood": {"backend": "none"},
}


class NotificationSendHandler:
    """
    Processa directives de notificacao.

    Topic: notification.send

    Payload esperado:
        order_ref: str — referencia do pedido
        template: str — nome do template (ex: "order_confirmed", "payment_expired")
        reason: str (opcional) — motivo (para templates de cancelamento)

    Roteamento por canal:
    1. Le Channel.config["notification_routing"] se existir
    2. Senao, usa Channel.config["notifications"]["backend"]
    3. Senao, usa DEFAULT_ROUTING por channel.ref
    4. Se backend="none": skip silenciosamente (ex: balcao, iFood)

    Idempotente: re-enviar notificacao e seguro (nao altera estado do pedido).
    """

    topic = "notification.send"

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Order

        payload = message.payload
        order_ref = payload.get("order_ref")
        template = payload.get("template", "generic")

        if not order_ref:
            logger.warning("NotificationSendHandler: missing order_ref in payload")
            message.status = "failed"
            message.last_error = "missing order_ref"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        try:
            order = Order.objects.select_related("channel").get(ref=order_ref)
        except Order.DoesNotExist:
            logger.warning("NotificationSendHandler: order %s not found", order_ref)
            message.status = "failed"
            message.last_error = f"Order not found: {order_ref}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        # Skip payment reminders if already paid
        if template == "payment.reminder":
            payment_status = order.data.get("payment", {}).get("status", "")
            if payment_status in ("paid", "captured", "succeeded") or order.status not in ("new", "created"):
                logger.info(
                    "NotificationSendHandler: skipping payment.reminder for order %s (already %s)",
                    order_ref, payment_status or order.status,
                )
                message.status = "done"
                message.save(update_fields=["status", "updated_at"])
                return

        # Resolve routing config for this channel
        routing = self._resolve_routing(order)
        backend_name = routing.get("backend")

        # Skip silently for channels that don't notify (balcao, iFood)
        if backend_name == "none" or not backend_name:
            logger.info(
                "NotificationSendHandler: skipping notification for order %s (channel=%s, backend=none)",
                order_ref, order.channel.ref,
            )
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        # Resolve recipient based on channel type
        recipient = self._resolve_recipient(order)

        if not recipient:
            logger.warning(
                "NotificationSendHandler: no recipient for order %s", order_ref,
            )
            message.status = "failed"
            message.last_error = "No recipient found"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        # Build context
        context = {
            "order_ref": order_ref,
            "template": template,
            "order_status": order.status,
            "total_q": order.total_q,
            "items": order.data.get("items", []),
            "reason": payload.get("reason"),
        }

        # Merge payment data if present
        payment = order.data.get("payment")
        if payment:
            context["payment"] = payment

        # For manychat backend, include subscriber_id in context
        if backend_name == "manychat" and order.handle_type == "manychat":
            context["subscriber_id"] = order.handle_ref

        result = notify(
            event=template,
            recipient=recipient,
            context=context,
            backend=backend_name,
        )

        if result.success:
            logger.info(
                "NotificationSendHandler: sent %s to %s for order %s (message_id=%s)",
                template, recipient[:15], order_ref, result.message_id,
            )
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
        else:
            logger.warning(
                "NotificationSendHandler: failed %s for order %s via %s: %s",
                template, order_ref, backend_name, result.error,
            )

            # Try fallback backend if available
            fallback = routing.get("fallback")
            if fallback and fallback != "none" and fallback != backend_name:
                logger.info(
                    "NotificationSendHandler: trying fallback %s for order %s",
                    fallback, order_ref,
                )
                fallback_result = notify(
                    event=template,
                    recipient=recipient,
                    context=context,
                    backend=fallback,
                )
                if fallback_result.success:
                    logger.info(
                        "NotificationSendHandler: fallback %s succeeded for order %s",
                        fallback, order_ref,
                    )
                    message.status = "done"
                    message.save(update_fields=["status", "updated_at"])
                    return

            message.last_error = (result.error or "unknown")[:500]
            if message.attempts >= 5:
                message.status = "failed"
            else:
                message.status = "queued"
            message.save(update_fields=["status", "last_error", "updated_at"])

    def _resolve_routing(self, order) -> dict:
        """
        Resolve notification routing config for an order's channel.

        Priority:
        1. Channel.config["notification_routing"]
        2. Channel.config["notifications"]["backend"] (legacy)
        3. DEFAULT_ROUTING[channel.ref]
        4. Empty dict (will skip)
        """
        config = order.channel.config or {}
        channel_ref = order.channel.ref

        # 1. notification_routing (new format)
        routing = config.get("notification_routing")
        if routing:
            return routing

        # 2. Legacy notifications.backend
        notifications = config.get("notifications", {})
        if notifications.get("backend"):
            return {"backend": notifications["backend"]}

        # 3. Default per channel
        return DEFAULT_ROUTING.get(channel_ref, {})

    def _resolve_recipient(self, order) -> str | None:
        """
        Resolve notification recipient based on order data.

        For manychat orders: use subscriber_id (handle_ref).
        For others: use phone from customer data.
        """
        # For manychat/whatsapp: subscriber_id is the direct recipient
        if order.handle_type == "manychat" and order.handle_ref:
            return order.handle_ref

        # Standard: phone from customer data
        return (
            order.data.get("customer", {}).get("phone")
            or order.data.get("customer_phone")
            or (order.handle_ref if order.handle_type in ("customer", "phone") else None)
        )
