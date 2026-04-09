"""
Notification handler — processa directives notification.send.

Suporta dois tipos de notificacao:
- Pedido: payload com order_ref → notifica cliente
- Sistema: payload com event (ex: stock.alert) → notifica operador

Roteamento phone-first (Brasil):
  manychat (WhatsApp) → sms → email → console
  Configurável via ChannelConfig.Notifications.fallback_chain
"""

from __future__ import annotations

import logging

from django.conf import settings

from shopman.notifications import notify
from shopman.omniman.models import Directive
from shopman.directives import NOTIFICATION_SEND

logger = logging.getLogger(__name__)


class NotificationSendHandler:
    """Processa directives de notificacao. Topic: notification.send"""

    topic = NOTIFICATION_SEND

    def handle(self, *, message: Directive, ctx: dict) -> None:
        payload = message.payload

        # Stock alert (no order_ref, has event field)
        if not payload.get("order_ref") and payload.get("event"):
            self._handle_system_notification(message)
            return

        self._handle_order_notification(message)

    def _handle_order_notification(self, message: Directive) -> None:
        """Handle order-related notifications (customer-facing)."""
        from shopman.omniman.models import Order

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

        backend_chain = self._resolve_backend_chain(order)

        if not backend_chain or backend_chain == ["none"]:
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        context = self._build_context(order, payload, template)
        template = self._qualify_template(template, context)
        context["template"] = template

        # Try each backend in the chain until one succeeds
        last_error = None
        for backend_name in backend_chain:
            if backend_name == "none":
                continue

            recipient = self._resolve_recipient(order, backend_name)
            if not recipient:
                last_error = f"No recipient for backend {backend_name}"
                continue

            # Enrich context for manychat
            if backend_name == "manychat" and order.handle_type == "manychat":
                context["subscriber_id"] = order.handle_ref

            result = notify(event=template, recipient=recipient, context=context, backend=backend_name)

            if result.success:
                message.status = "done"
                message.save(update_fields=["status", "updated_at"])
                return

            last_error = result.error or "unknown"
            logger.info(
                "Notification backend %s failed for %s, trying next in chain",
                backend_name, order_ref,
            )

        # All backends in chain failed
        message.last_error = (last_error or "all backends failed")[:500]
        exhausted = message.attempts >= 5
        message.status = "failed" if exhausted else "queued"
        message.save(update_fields=["status", "last_error", "updated_at"])

        if exhausted:
            self._escalate(order_ref, template, last_error)

    def _escalate(self, order_ref: str, template: str, last_error: str | None) -> None:
        """Create OperatorAlert when notification delivery is exhausted."""
        try:
            from shopman.models import OperatorAlert

            OperatorAlert.objects.create(
                type="notification_failed",
                severity="error",
                message=(
                    f"Notificação '{template}' falhou após 5 tentativas "
                    f"para pedido {order_ref}. Último erro: {last_error or 'desconhecido'}"
                ),
                order_ref=order_ref or "",
            )
            logger.warning(
                "notification_escalated order=%s template=%s",
                order_ref, template,
            )
        except Exception:
            logger.exception("Failed to create OperatorAlert for notification failure")

    def _handle_system_notification(self, message: Directive) -> None:
        """Handle system notifications (stock alerts, etc.) — routed to operator."""
        payload = message.payload
        event = payload.get("event", "system")
        context = payload.get("context", {})

        # Normalize event → template name (stock.alert.triggered → stock_alert)
        if "stock.alert" in event:
            template = "stock_alert"
        else:
            template = context.get("template") or event

        # Determine recipient: operator email from settings or DEFAULT_FROM_EMAIL
        recipient = getattr(settings, "SHOPMAN_OPERATOR_EMAIL", None) or getattr(
            settings, "DEFAULT_FROM_EMAIL", "admin@shopman.local"
        )

        # System notifications: email → console
        for backend_name in ["email", "console"]:
            result = notify(event=template, recipient=recipient, context=context, backend=backend_name)
            if result.success:
                message.status = "done"
                message.save(update_fields=["status", "updated_at"])
                return

        message.last_error = (result.error or "unknown")[:500]
        exhausted = message.attempts >= 5
        message.status = "failed" if exhausted else "queued"
        message.save(update_fields=["status", "last_error", "updated_at"])

        if exhausted:
            self._escalate("", event, result.error)

    def _resolve_backend_chain(self, order) -> list[str]:
        """Resolve the ordered list of backends to try via ChannelConfig cascade."""
        from shopman.config import ChannelConfig

        notifications = ChannelConfig.for_channel(order.channel).notifications
        backend = notifications.backend or "manychat"
        chain = notifications.fallback_chain or []
        return [backend] + [b for b in chain if b != backend]

    def _build_context(self, order, payload: dict, template: str) -> dict:
        """Build notification context from order data."""
        fulfillment_type = order.data.get("fulfillment_type", "pickup")

        context = {
            "order_ref": payload.get("order_ref"),
            "template": template,
            "order_status": order.status,
            "total_q": order.total_q,
            "items": order.snapshot.get("items", []),
            "reason": payload.get("reason"),
            "fulfillment_type": fulfillment_type,
        }

        # Enrich with customer name
        customer_data = order.data.get("customer", {})
        if isinstance(customer_data, dict):
            context["customer_name"] = customer_data.get("name", "")
        context["customer_phone"] = (
            customer_data.get("phone", "") if isinstance(customer_data, dict) else ""
        )

        # Format total for display
        if order.total_q:
            context["total"] = f"R$ {order.total_q / 100:,.2f}"

        payment = order.data.get("payment")
        if payment:
            context["payment"] = payment

        return context

    @staticmethod
    def _qualify_template(template: str, context: dict) -> str:
        """Qualify template name based on fulfillment_type when relevant.

        order_ready → order_ready_pickup or order_ready_delivery
        """
        if template in ("order_ready", "order.ready"):
            ft = context.get("fulfillment_type", "pickup")
            suffix = "delivery" if ft == "delivery" else "pickup"
            return f"{template}_{suffix}"
        return template

    def _resolve_recipient(self, order, backend_name: str = "") -> str | None:
        """Resolve recipient based on backend type.

        manychat → handle_ref (subscriber_id) ou phone
        email    → email ou phone
        sms      → phone
        console  → phone ou qualquer identificador
        """
        customer_data = order.data.get("customer", {})
        if not isinstance(customer_data, dict):
            customer_data = {}

        if backend_name == "manychat":
            # Manychat: subscriber_id preferido, depois phone
            if order.handle_type == "manychat" and order.handle_ref:
                return order.handle_ref
            return customer_data.get("phone") or order.data.get("customer_phone")

        if backend_name == "email":
            # Email: email preferido, depois phone como fallback
            email = customer_data.get("email")
            if email:
                return email
            return customer_data.get("phone") or order.data.get("customer_phone")

        # sms, console, webhook, etc: phone
        return (
            customer_data.get("phone")
            or order.data.get("customer_phone")
            or (order.handle_ref if order.handle_type in ("customer", "phone") else None)
        )


__all__ = ["NotificationSendHandler"]
