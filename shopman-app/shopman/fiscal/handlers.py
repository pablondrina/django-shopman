"""
Shopman Fiscal Handlers — Handlers de diretiva para emissão fiscal.
"""

from __future__ import annotations

import logging

from shopman.ordering.models import Directive
from shopman.ordering.protocols import FiscalBackend

logger = logging.getLogger(__name__)


class NFCeEmitHandler:
    """
    Directive handler para emissão de NFC-e.

    Topic: fiscal.emit_nfce
    Payload: {order_ref, items, customer?, payment, additional_info?}

    Fluxo:
    1. Order completa pagamento → Directive(fiscal.emit_nfce) criada.
    2. Handler processa → chama FiscalBackend.emit().
    3. Se autorizado → salva access_key no Order.metadata.
    4. Se erro → Directive falha → retry automático (at-least-once).
    """

    topic = "fiscal.emit_nfce"

    def __init__(self, backend: FiscalBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Order

        payload = message.payload
        order_ref = payload["order_ref"]

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist:
            message.status = "failed"
            message.last_error = "Order not found"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        # Idempotência: verifica se já emitiu
        if order.data.get("nfce_access_key"):
            logger.info("NFC-e already emitted for %s", order_ref)
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        result = self.backend.emit(
            reference=order_ref,
            items=payload["items"],
            customer=payload.get("customer"),
            payment=payload["payment"],
            additional_info=payload.get("additional_info"),
        )

        if result.success:
            order.data["nfce_access_key"] = result.access_key
            order.data["nfce_number"] = result.document_number
            order.data["nfce_danfe_url"] = result.danfe_url
            order.data["nfce_qrcode_url"] = result.qrcode_url
            order.save(update_fields=["data", "updated_at"])

            logger.info(
                "NFC-e authorized: %s → %s", order_ref, result.access_key,
            )
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
        else:
            message.status = "failed"
            message.last_error = f"NFC-e emission failed: {result.error_message}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            raise RuntimeError(
                f"NFC-e emission failed: {result.error_message}"
            )


class NFCeCancelHandler:
    """
    Directive handler para cancelamento de NFC-e.

    Topic: fiscal.cancel_nfce
    Payload: {order_ref, reason}
    """

    topic = "fiscal.cancel_nfce"

    def __init__(self, backend: FiscalBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Order

        payload = message.payload
        order_ref = payload["order_ref"]
        reason = payload["reason"]

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist:
            message.status = "failed"
            message.last_error = "Order not found"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        # Idempotência: verifica se já cancelou
        if order.data.get("nfce_cancelled"):
            logger.info("NFC-e already cancelled for %s", order_ref)
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        result = self.backend.cancel(
            reference=order_ref,
            reason=reason,
        )

        if result.success:
            order.data["nfce_cancelled"] = True
            order.data["nfce_cancellation_protocol"] = result.protocol_number
            order.save(update_fields=["data", "updated_at"])

            logger.info("NFC-e cancelled: %s", order_ref)
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
        else:
            message.status = "failed"
            message.last_error = f"NFC-e cancellation failed: {result.error_message}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            raise RuntimeError(
                f"NFC-e cancellation failed: {result.error_message}"
            )
