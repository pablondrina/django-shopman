"""
Preorder handler — dispara o trabalho físico da encomenda NA data dela.

O lifecycle adia KDS e baixa de estoque de pedidos com ``delivery_date``
futura (``_on_confirmed``/``_on_paid`` agendam ``preorder.activate`` com
``available_at`` na meia-noite da data). Este handler é o despertador:
na manhã da data, cria os tickets e baixa o que já materializou —
``lifecycle.activate_preorder`` faz exatamente o que a confirmação teria
feito se a data fosse hoje.
"""

from __future__ import annotations

import logging

from shopman.orderman.models import Directive

from shopman.shop.directives import PREORDER_ACTIVATE

logger = logging.getLogger(__name__)


class PreorderActivateHandler:
    """Ativa encomenda na data. Topic: preorder.activate"""

    topic = PREORDER_ACTIVATE

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.models import Order

        from shopman.shop.lifecycle import activate_preorder

        order_ref = message.payload.get("order_ref")
        if not order_ref:
            return

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist:
            logger.info("preorder.activate: order %s não existe mais", order_ref)
            return

        activate_preorder(order)
