"""
Fiscal handlers — emissão e cancelamento de NFC-e.

Tratamento de erro de produção:
- Falha de transporte/5xx/processando → ``DirectiveTransientError`` (retry com
  backoff); rejeição/payload/4xx → ``DirectiveTerminalError`` (visível na fila).
- Retry NUNCA re-POSTa cego: consulta ``query_status`` primeiro. Um timeout
  pós-emissão deixa a nota autorizada na SEFAZ com o mesmo ``ref`` — o re-POST
  responderia 422 ("referência já utilizada") para sempre e a nota ficaria órfã.
"""

from __future__ import annotations

import logging

from shopman.fiscalman.contracts import FiscalBackend, FiscalDocumentResult
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive

from shopman.shop.directives import FISCAL_CANCEL_NFCE, FISCAL_EMIT_NFCE

logger = logging.getLogger(__name__)

# Códigos que retry pode curar: transporte fora do ar, 5xx, rate limit e
# "processando_autorizacao" (async da SEFAZ). Qualquer 4xx/payload é terminal.
_TRANSIENT_PREFIXES = ("focus_nfe_http_5",)
_TRANSIENT_CODES = {
    "focus_nfe_http_error",
    "focus_nfe_http_429",
    "focus_nfe_http_408",
    "focus_nfe_processing",
}
_REFERENCE_CONFLICT_CODES = {"focus_nfe_http_422"}


def _is_transient(error_code: str | None) -> bool:
    code = str(error_code or "")
    return code in _TRANSIENT_CODES or code.startswith(_TRANSIENT_PREFIXES)


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

        if order.status in (Order.Status.CANCELLED, Order.Status.RETURNED):
            raise DirectiveTerminalError(
                f"Pedido {order_ref} está {order.status}: não emitir NFC-e."
            )

        # Retry: o POST anterior pode ter emitido e a resposta se perdido
        # (timeout/worker morto). Consultar antes de re-POSTar com o mesmo ref.
        if int(getattr(message, "attempts", 0) or 0) > 0:
            if self._adopt_existing(order, order_ref):
                return

        result = self.backend.emit(
            reference=order_ref, items=payload["items"],
            customer=payload.get("customer"), payment=payload["payment"],
            additional_info=payload.get("additional_info"),
        )

        if result.success:
            self._record(order, result)
            return

        if result.error_code in _REFERENCE_CONFLICT_CODES:
            # "Referência já utilizada": a nota EXISTE no Focus — adotar.
            if self._adopt_existing(order, order_ref):
                return
            raise DirectiveTerminalError(
                f"NFC-e emission failed: ref em conflito e consulta não autorizada "
                f"({result.error_message})"
            )

        if _is_transient(result.error_code):
            raise DirectiveTransientError(
                f"NFC-e emission transient ({result.error_code}): {result.error_message}"
            )
        raise DirectiveTerminalError(f"NFC-e emission failed: {result.error_message}")

    def _adopt_existing(self, order, order_ref: str) -> bool:
        """Consulta o Focus pelo ref; se autorizada, adota a nota existente."""
        query = getattr(self.backend, "query_status", None)
        if query is None:
            return False
        status = query(reference=order_ref)
        if status.success and status.access_key:
            self._record(order, status)
            logger.info("fiscal.emit: nota existente adotada via consulta order=%s", order_ref)
            return True
        return False

    @staticmethod
    def _record(order, result: FiscalDocumentResult) -> None:
        order.data["nfce_access_key"] = result.access_key
        order.data["nfce_number"] = result.document_number
        order.data["nfce_series"] = result.document_series
        order.data["nfce_protocol"] = result.protocol_number
        order.data["nfce_xml_url"] = result.xml_url
        order.data["nfce_danfe_url"] = result.danfe_url
        order.data["nfce_qrcode_url"] = result.qrcode_url
        order.data["nfce_status"] = result.status
        order.save(update_fields=["data", "updated_at"])


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

        if _is_transient(result.error_code):
            raise DirectiveTransientError(
                f"NFC-e cancellation transient ({result.error_code}): {result.error_message}"
            )

        # Nota válida em pé para venda cancelada é passivo fiscal — o operador
        # PRECISA saber (fora da janela da SEFAZ o caminho é outro documento).
        self._alert_cancel_failed(order, result)
        raise DirectiveTerminalError(f"NFC-e cancellation failed: {result.error_message}")

    @staticmethod
    def _alert_cancel_failed(order, result) -> None:
        from shopman.shop.services.observability import create_operator_alert

        create_operator_alert(
            type="fiscal_cancel_failed",
            severity="critical",
            message=(
                f"Cancelamento da NFC-e do pedido {order.ref} FALHOU "
                f"({result.error_message}). A nota continua válida na SEFAZ — "
                "resolver com o contador (cancelamento fora da janela exige outro instrumento)."
            ),
            order_ref=order.ref,
            dedupe_key=f"fiscal_cancel_failed:{order.ref}",
        )


__all__ = ["NFCeEmitHandler", "NFCeCancelHandler"]
