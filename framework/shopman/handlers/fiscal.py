"""
Fiscal handlers — emissão e cancelamento de NFC-e.

Inline de shopman.fiscal.handlers.
"""

from __future__ import annotations

import logging

from shopman.omniman.models import Directive
from shopman.omniman.protocols import FiscalBackend
from shopman.topics import FISCAL_CANCEL_NFCE, FISCAL_EMIT_NFCE

logger = logging.getLogger(__name__)


class NFCeEmitHandler:
    """Directive handler para emissão de NFC-e. Topic: fiscal.emit_nfce"""

    topic = FISCAL_EMIT_NFCE

    def __init__(self, backend: FiscalBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.omniman.models import Order

        payload = message.payload
        order_ref = payload["order_ref"]

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist:
            message.status = "failed"
            message.last_error = "Order not found"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        if order.data.get("nfce_access_key"):
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        result = self.backend.emit(
            reference=order_ref, items=payload["items"],
            customer=payload.get("customer"), payment=payload["payment"],
            additional_info=payload.get("additional_info"),
        )

        if result.success:
            order.data["nfce_access_key"] = result.access_key
            order.data["nfce_number"] = result.document_number
            order.data["nfce_danfe_url"] = result.danfe_url
            order.data["nfce_qrcode_url"] = result.qrcode_url
            order.save(update_fields=["data", "updated_at"])
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
        else:
            message.status = "failed"
            message.last_error = f"NFC-e emission failed: {result.error_message}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            raise RuntimeError(f"NFC-e emission failed: {result.error_message}")


class NFCeCancelHandler:
    """Directive handler para cancelamento de NFC-e. Topic: fiscal.cancel_nfce"""

    topic = FISCAL_CANCEL_NFCE

    def __init__(self, backend: FiscalBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.omniman.models import Order

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

        if order.data.get("nfce_cancelled"):
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        result = self.backend.cancel(reference=order_ref, reason=reason)

        if result.success:
            order.data["nfce_cancelled"] = True
            order.data["nfce_cancellation_protocol"] = result.protocol_number
            order.save(update_fields=["data", "updated_at"])
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
        else:
            message.status = "failed"
            message.last_error = f"NFC-e cancellation failed: {result.error_message}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            raise RuntimeError(f"NFC-e cancellation failed: {result.error_message}")


__all__ = ["NFCeEmitHandler", "NFCeCancelHandler"]
