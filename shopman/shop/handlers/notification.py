"""
Notification handler — processa directives notification.send.

Suporta dois tipos de notificação:
- Pedido: payload com order_ref → delega para services.notification.deliver_order_notification()
- Sistema: payload com event (ex: stock.alert) → notifica operador via email/console

O handler é fino: lê o directive, obtém o pedido, delega ao service, escreve o status.
"""

from __future__ import annotations

import logging

from django.conf import settings
from shopman.orderman.models import Directive

from shopman.shop.directives import NOTIFICATION_SEND
from shopman.shop.notifications import notify
from shopman.shop.services import notification as notification_svc

logger = logging.getLogger(__name__)


class NotificationSendHandler:
    """Processa directives de notificação. Topic: notification.send"""

    topic = NOTIFICATION_SEND

    def handle(self, *, message: Directive, ctx: dict) -> None:
        payload = message.payload

        # Stock alert (no order_ref, has event field)
        if not payload.get("order_ref") and payload.get("event"):
            self._handle_system_notification(message)
            return

        self._handle_order_notification(message)

    def _handle_order_notification(self, message: Directive) -> None:
        """Handle order-related notifications — delega ao service."""
        from shopman.orderman.models import Order

        from shopman.shop.services import payment as payment_svc

        payload = message.payload
        order_ref = payload.get("order_ref")
        template = payload.get("template", "generic")

        if not order_ref:
            message.status = "failed"
            message.last_error = "missing order_ref"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist:
            message.status = "failed"
            message.last_error = f"Order not found: {order_ref}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        # Guarda: pular reminders de pagamento se já pago
        if template == "payment.reminder":
            payment_status = payment_svc.get_payment_status(order) or ""
            if payment_status in ("paid", "captured", "succeeded") or order.status not in ("new", "created"):
                message.status = "done"
                message.save(update_fields=["status", "updated_at"])
                return

        success, last_error = notification_svc.deliver_order_notification(order, template, payload)

        if success:
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        # Todos os backends falharam
        message.last_error = (last_error or "all backends failed")[:500]
        exhausted = message.attempts >= 5
        message.status = "failed" if exhausted else "queued"
        message.save(update_fields=["status", "last_error", "updated_at"])

        if exhausted:
            self._escalate(order_ref, template, last_error)

    def _escalate(self, order_ref: str, template: str, last_error: str | None) -> None:
        """Cria OperatorAlert quando entrega de notificação é exaurida."""
        try:
            from shopman.backstage.models import OperatorAlert

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

        recipient = getattr(settings, "SHOPMAN_OPERATOR_EMAIL", None) or getattr(
            settings, "DEFAULT_FROM_EMAIL", "admin@shopman.local"
        )

        result = None
        for backend_name in ["email", "console"]:
            result = notify(event=template, recipient=recipient, context=context, backend=backend_name)
            if result.success:
                message.status = "done"
                message.save(update_fields=["status", "updated_at"])
                return

        message.last_error = (result.error if result else "unknown")[:500]
        exhausted = message.attempts >= 5
        message.status = "failed" if exhausted else "queued"
        message.save(update_fields=["status", "last_error", "updated_at"])

        if exhausted:
            self._escalate("", event, result.error if result else None)


__all__ = ["NotificationSendHandler"]
