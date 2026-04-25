"""
Fiscal handlers — emissão e cancelamento de NFC-e.

Inline de shopman.fiscal.handlers.
"""

from __future__ import annotations

import logging

from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Directive
from shopman.orderman.protocols import FiscalBackend

from shopman.shop.directives import FISCAL_CANCEL_NFCE, FISCAL_EMIT_NFCE

logger = logging.getLogger(__name__)


class NFCeEmitHandler:
    """Directive handler para emissão de NFC-e. Topic: fiscal.emit_nfce"""

    topic = FISCAL_EMIT_NFCE

    def __init__(self, backend: FiscalBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.models import Order

        payload = message.payload
        order_ref = payload["order_ref"]

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist as exc:
            raise DirectiveTerminalError("Order not found") from exc

        if order.data.get("nfce_access_key"):
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
            return

        raise DirectiveTerminalError(f"NFC-e emission failed: {result.error_message}")


class NFCeCancelHandler:
    """Directive handler para cancelamento de NFC-e. Topic: fiscal.cancel_nfce"""

    topic = FISCAL_CANCEL_NFCE

    def __init__(self, backend: FiscalBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.models import Order

        payload = message.payload
        order_ref = payload["order_ref"]
        reason = payload["reason"]

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist as exc:
            raise DirectiveTerminalError("Order not found") from exc

        if order.data.get("nfce_cancelled"):
            return

        result = self.backend.cancel(reference=order_ref, reason=reason)

        if result.success:
            order.data["nfce_cancelled"] = True
            order.data["nfce_cancellation_protocol"] = result.protocol_number
            order.save(update_fields=["data", "updated_at"])
            return

        raise DirectiveTerminalError(f"NFC-e cancellation failed: {result.error_message}")


__all__ = ["NFCeEmitHandler", "NFCeCancelHandler"]
