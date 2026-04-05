"""
Confirmation handler — auto-confirma pedido após timeout.

Inline de shopman.confirmation.handlers.
"""

from __future__ import annotations

import logging
from datetime import datetime

from django.utils import timezone

from shopman.ordering.models import Directive
from shopman.topics import CONFIRMATION_TIMEOUT

logger = logging.getLogger(__name__)


class ConfirmationTimeoutHandler:
    """Confirma pedido automaticamente se operador não cancelar em tempo. Topic: confirmation.timeout"""

    topic = CONFIRMATION_TIMEOUT

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Order

        payload = message.payload
        order_ref = payload["order_ref"]
        expires_at = datetime.fromisoformat(payload["expires_at"])

        if not timezone.is_aware(expires_at):
            expires_at = timezone.make_aware(expires_at)

        if timezone.now() < expires_at:
            message.available_at = expires_at
            message.save(update_fields=["available_at", "updated_at"])
            return

        try:
            order = Order.objects.select_related("channel").get(ref=order_ref)
        except Order.DoesNotExist:
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        if order.status != Order.Status.NEW:
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        order.transition_status(Order.Status.CONFIRMED, actor="confirmation.timeout")
        message.status = "done"
        message.save(update_fields=["status", "updated_at"])


__all__ = ["ConfirmationTimeoutHandler"]
