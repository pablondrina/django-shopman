from __future__ import annotations

import logging
from datetime import datetime

from django.utils import timezone

from shopman.ordering.holds import release_holds_for_order
from shopman.ordering.models import Directive

logger = logging.getLogger(__name__)


class ConfirmationTimeoutHandler:
    """
    Confirma pedido automaticamente se operador não cancelar em tempo.

    Topic: confirmation.timeout

    Confirmação OTIMISTA: o operador tem N minutos para cancelar ativamente.
    Se não fizer nada, o pedido é auto-confirmado e segue para pagamento.

    Idempotente: verifica status atual antes de agir.
    Só auto-confirma orders que ainda estejam em NEW.
    """

    topic = "confirmation.timeout"

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Order

        payload = message.payload
        order_ref = payload["order_ref"]
        expires_at = datetime.fromisoformat(payload["expires_at"])

        if not timezone.is_aware(expires_at):
            expires_at = timezone.make_aware(expires_at)

        if timezone.now() < expires_at:
            # Ainda não expirou — requeue para verificar depois
            message.available_at = expires_at
            message.save(update_fields=["available_at", "updated_at"])
            return

        try:
            order = Order.objects.select_related("channel").get(ref=order_ref)
        except Order.DoesNotExist:
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        # Idempotência: só age se ainda estiver em NEW
        if order.status != Order.Status.NEW:
            logger.info(
                "ConfirmationTimeoutHandler: order %s already in status %s, skipping.",
                order_ref, order.status,
            )
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        # Confirmação otimista: auto-confirma (operador não cancelou a tempo)
        order.transition_status(Order.Status.CONFIRMED, actor="confirmation.timeout")

        logger.info("ConfirmationTimeoutHandler: order %s auto-confirmed (optimistic timeout).", order_ref)
        message.status = "done"
        message.save(update_fields=["status", "updated_at"])
