"""
Confirmation handler — resolve a NEW order after its confirmation timeout.

Fires once a ``confirmation.timeout`` directive reaches its ``expires_at``.
The terminal action is dictated by ``payload["action"]``:

- ``confirm`` → auto-confirm the order (auto_confirm mode).
- ``cancel``  → auto-cancel the order (auto_cancel mode).

If the operator has already moved the order out of ``NEW`` (by explicitly
confirming or cancelling within the window) the handler noops.
"""

from __future__ import annotations

import logging
from datetime import datetime

from django.utils import timezone
from shopman.orderman.models import Directive

from shopman.shop.directives import CONFIRMATION_TIMEOUT, ORDER_STALE_NEW_ALERT

logger = logging.getLogger(__name__)


class ConfirmationTimeoutHandler:
    """Resolve pedido após timeout de confirmação. Topic: confirmation.timeout"""

    topic = CONFIRMATION_TIMEOUT

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.models import Order

        from shopman.shop.lifecycle import ensure_confirmable

        payload = message.payload
        order_ref = payload["order_ref"]
        action = payload.get("action", "confirm")
        expires_at = datetime.fromisoformat(payload["expires_at"])

        if not timezone.is_aware(expires_at):
            expires_at = timezone.make_aware(expires_at)

        if timezone.now() < expires_at:
            message.available_at = expires_at
            message.save(update_fields=["available_at", "updated_at"])
            return

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist:
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        if order.status != Order.Status.NEW:
            # Operator already resolved the order within the window — noop.
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        if action == "confirm":
            ensure_confirmable(order)
            order.transition_status(
                Order.Status.CONFIRMED, actor="confirmation.timeout",
            )
        elif action == "cancel":
            order.transition_status(
                Order.Status.CANCELLED, actor="confirmation.timeout",
            )
            logger.info(
                "confirmation.timeout: auto-cancelled order %s (auto_cancel mode)",
                order_ref,
            )
        else:
            logger.error(
                "confirmation.timeout: unknown action %r for order %s",
                action, order_ref,
            )
            message.status = "failed"
            message.save(update_fields=["status", "updated_at"])
            return

        message.status = "done"
        message.save(update_fields=["status", "updated_at"])


class StaleNewOrderAlertHandler:
    """Alerta o operador quando um pedido manual fica parado em NEW por muito tempo.

    Topic: order.stale_new_alert

    Disparado por :func:`_handle_confirmation` em modo `manual` (iFood etc.).
    Cria um OperatorAlert("stale_new_order") apenas se o pedido ainda estiver
    em NEW — caso já tenha sido resolvido, noop.
    """

    topic = ORDER_STALE_NEW_ALERT

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.models import Order
        from shopman.backstage.models import OperatorAlert

        payload = message.payload
        order_ref = payload["order_ref"]
        alert_at = datetime.fromisoformat(payload["alert_at"])
        if not timezone.is_aware(alert_at):
            alert_at = timezone.make_aware(alert_at)

        if timezone.now() < alert_at:
            message.available_at = alert_at
            message.save(update_fields=["available_at", "updated_at"])
            return

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist:
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        if order.status != Order.Status.NEW:
            # Operador já resolveu — nada a fazer.
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        try:
            OperatorAlert.objects.create(
                type="stale_new_order",
                severity="warning",
                message=f"Pedido {order.ref} aguardando decisão há muito tempo",
                order_ref=order.ref,
            )
        except Exception:
            logger.exception("stale_new_alert: failed to create alert for order %s", order_ref)

        message.status = "done"
        message.save(update_fields=["status", "updated_at"])


__all__ = ["ConfirmationTimeoutHandler", "StaleNewOrderAlertHandler"]
