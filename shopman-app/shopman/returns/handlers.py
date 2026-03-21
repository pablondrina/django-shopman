"""
Shopman Return Handler -- Handler de diretiva para devoluções.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from shopman.ordering.models import Directive

logger = logging.getLogger(__name__)


class ReturnHandler:
    """
    Directive handler para processamento de devoluções.

    Topic: return.process
    Payload: {order_ref, items, reason, refund_total_q, return_index}

    Fluxo:
    1. ReturnService.initiate_return() cria Directive(return.process).
    2. Handler processa:
       a. Reversão de estoque via StockBackend.receive_return()
       b. Reembolso via ReturnService.process_refund()
    3. Marca return_record como refund_processed.

    Idempotência:
    - Verifica order.data["returns"][index]["refund_processed"]
    - Se True, pula processamento.
    """

    topic = "return.process"

    def __init__(self, *, stock_backend=None, payment_backend=None, fiscal_backend=None):
        self.stock_backend = stock_backend
        self.payment_backend = payment_backend
        self.fiscal_backend = fiscal_backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Order

        from .service import ReturnService

        payload = message.payload
        order_ref = payload["order_ref"]
        items = payload["items"]
        refund_total_q = payload["refund_total_q"]
        return_index = payload.get("return_index", 0)

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist:
            message.status = "failed"
            message.last_error = f"Order not found: {order_ref}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        # Idempotência: verifica se já processou
        returns = order.data.get("returns", [])
        if return_index < len(returns) and returns[return_index].get("refund_processed"):
            logger.info("Return already processed for %s index %d", order_ref, return_index)
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        # 1. Reversão de estoque
        if self.stock_backend:
            for item in items:
                try:
                    self.stock_backend.receive_return(
                        sku=item["sku"],
                        quantity=Decimal(str(item["qty"])),
                        reference=order_ref,
                        reason=f"Devolução pedido {order_ref}",
                    )
                except Exception:
                    logger.exception(
                        "ReturnHandler: Failed to reverse stock for sku=%s order=%s",
                        item["sku"], order_ref,
                    )

        # 2. Reembolso + fiscal
        try:
            ReturnService.process_refund(
                order=order,
                amount_q=refund_total_q,
                actor="return.process",
                payment_backend=self.payment_backend,
                fiscal_backend=self.fiscal_backend,
            )
        except Exception:
            logger.exception("ReturnHandler: Failed to process refund for order=%s", order_ref)
            message.status = "failed"
            message.last_error = "Refund processing failed"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        # 3. Marca como processado
        order.refresh_from_db()
        returns = order.data.get("returns", [])
        if return_index < len(returns):
            returns[return_index]["refund_processed"] = True
            order.data["returns"] = returns
            order.save(update_fields=["data", "updated_at"])

        message.status = "done"
        message.save(update_fields=["status", "updated_at"])

        logger.info(
            "ReturnHandler: Completed return for order=%s refund_q=%d",
            order_ref, refund_total_q,
        )
