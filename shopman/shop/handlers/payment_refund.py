"""Retry assíncrono de estorno — completa o fail-loud com retry+backoff.

Topic: payment.refund
Payload: {order_ref, amount_q?, idempotency_key?}

O caminho síncrono (payment.refund) enfileira este directive numa falha TRANSIENTE
de gateway. O handler reexecuta o estorno (idempotente via idempotency_key); em
nova falha transiente propaga DirectiveTransientError para o engine retentar com
backoff. Ao esgotar as tentativas, alerta o operador (o engine não auto-alerta).
"""

from __future__ import annotations

import logging

from shopman.orderman.dispatch import MAX_ATTEMPTS
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive

from shopman.shop.directives import PAYMENT_REFUND

logger = logging.getLogger(__name__)


class PaymentRefundHandler:
    topic = PAYMENT_REFUND

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.models import Order

        from shopman.shop.services import payment

        payload = message.payload
        order_ref = payload.get("order_ref")
        if not order_ref:
            raise DirectiveTerminalError("missing order_ref")

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist as exc:
            raise DirectiveTerminalError(f"Order not found: {order_ref}") from exc

        try:
            payment.refund(
                order,
                amount_q=payload.get("amount_q"),
                idempotency_key=payload.get("idempotency_key"),
                _from_directive=True,
            )
        except DirectiveTransientError:
            # Última tentativa (attempts é incrementado ANTES do handle): o engine vai
            # marcar failed. Alerta o operador antes de propagar — o dinheiro pode
            # estar retido e ninguém mais avisa.
            if message.attempts >= MAX_ATTEMPTS:
                intent_ref = (order.data or {}).get("payment", {}).get("intent_ref")
                payment._alert_refund_failed(
                    order, intent_ref, payload.get("amount_q"),
                    "tentativas de estorno esgotadas",
                )
            raise
