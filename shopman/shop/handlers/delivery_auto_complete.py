"""Delivery auto-complete handler — fecha um pedido em entrega após ETA + folga.

Rede de segurança do trecho sem rastreio: se nem o cliente ("Recebi") nem o
operador ("Marcar entregue") fecharem o loop, o pedido não fica preso em "saiu
para entrega". Revalida o estado, então é um no-op se o pedido já foi fechado.
"""

from __future__ import annotations

from shopman.orderman.models import Directive

from shopman.shop.directives import DELIVERY_AUTO_COMPLETE


class DeliveryAutoCompleteHandler:
    """Marca como entregue um pedido ainda em entrega quando o prazo vence."""

    topic = DELIVERY_AUTO_COMPLETE

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.models import Order

        from shopman.shop.services import operator_orders

        payload = message.payload or {}
        try:
            order = Order.objects.get(ref=payload["order_ref"])
        except (KeyError, Order.DoesNotExist):
            return

        # confirm_received é idempotente: só age se ainda está em entrega
        # (dispatched + delivery). Mesma transição do operador → notifica 1×.
        operator_orders.confirm_received(order, actor="delivery.auto_complete")


__all__ = ["DeliveryAutoCompleteHandler"]
