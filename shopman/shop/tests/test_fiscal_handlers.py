"""Handlers fiscais (NFC-e): transiente vs terminal, reconciliação e guardas.

Regressões do audit pré-go-live (não havia NENHUM teste de handler fiscal):
- timeout/5xx do Focus virava falha TERMINAL (retry existia e não era usado);
- retry re-POSTava com o mesmo ref → 422 eterno e nota autorizada ÓRFÃ na
  SEFAZ (query_status existia e nunca era chamado);
- era possível emitir NFC-e para pedido CANCELADO;
- falha terminal de cancelamento era invisível ao operador.
"""

from __future__ import annotations

import pytest
from shopman.fiscalman.contracts import FiscalCancellationResult, FiscalDocumentResult
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive, Order

from shopman.backstage.models import OperatorAlert
from shopman.shop.handlers.fiscal import NFCeCancelHandler, NFCeEmitHandler
from shopman.shop.models import Channel

pytestmark = pytest.mark.django_db

AUTHORIZED = FiscalDocumentResult(
    success=True,
    access_key="4125" + "0" * 40,
    document_number=42,
    document_series=3,
    protocol_number="135250000000000",
    status="authorized",
)


class FakeBackend:
    def __init__(self, *, emit_result=None, query_result=None, cancel_result=None):
        self.emit_result = emit_result
        self.query_result = query_result
        self.cancel_result = cancel_result
        self.emit_calls = 0
        self.query_calls = 0
        self.cancel_calls = 0

    def emit(self, **kwargs):
        self.emit_calls += 1
        return self.emit_result

    def query_status(self, *, reference):
        self.query_calls += 1
        return self.query_result

    def cancel(self, *, reference, reason):
        self.cancel_calls += 1
        return self.cancel_result


def _error(code, message="boom"):
    return FiscalDocumentResult(success=False, status="denied", error_code=code, error_message=message)


@pytest.fixture
def order(db):
    Channel.objects.create(ref="pdv", name="PDV")
    return Order.objects.create(
        ref="ORD-FISCAL-1",
        channel_ref="pdv",
        status=Order.Status.CONFIRMED,
        total_q=5000,
        data={"fiscal": {"issue_document": True}},
    )


def _emit_directive(order, attempts=0):
    return Directive.objects.create(
        topic="fiscal.emit_nfce",
        payload={"order_ref": order.ref, "items": [], "payment": {"method": "cash", "amount_q": 5000}},
        attempts=attempts,
    )


def test_timeout_is_transient_not_terminal(order):
    backend = FakeBackend(emit_result=_error("focus_nfe_http_error"))
    with pytest.raises(DirectiveTransientError):
        NFCeEmitHandler(backend).handle(message=_emit_directive(order), ctx={})


def test_5xx_is_transient_and_4xx_is_terminal(order):
    with pytest.raises(DirectiveTransientError):
        NFCeEmitHandler(FakeBackend(emit_result=_error("focus_nfe_http_503"))).handle(
            message=_emit_directive(order), ctx={}
        )
    with pytest.raises(DirectiveTerminalError):
        NFCeEmitHandler(FakeBackend(emit_result=_error("focus_nfe_http_400"))).handle(
            message=_emit_directive(order), ctx={}
        )


def test_retry_queries_before_reposting_and_adopts_orphan(order):
    # 1ª tentativa deu timeout DEPOIS da SEFAZ autorizar. O retry deve
    # consultar e adotar a nota existente — nunca re-POSTar (422 eterno).
    backend = FakeBackend(query_result=AUTHORIZED)
    NFCeEmitHandler(backend).handle(message=_emit_directive(order, attempts=1), ctx={})

    assert backend.query_calls == 1
    assert backend.emit_calls == 0
    order.refresh_from_db()
    assert order.data["nfce_access_key"] == AUTHORIZED.access_key
    assert order.data["nfce_status"] == "authorized"


def test_reference_conflict_falls_back_to_query(order):
    backend = FakeBackend(emit_result=_error("focus_nfe_http_422"), query_result=AUTHORIZED)
    NFCeEmitHandler(backend).handle(message=_emit_directive(order), ctx={})

    order.refresh_from_db()
    assert order.data["nfce_access_key"] == AUTHORIZED.access_key


def test_cancelled_order_never_emits(order):
    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status"])
    backend = FakeBackend(emit_result=AUTHORIZED)

    with pytest.raises(DirectiveTerminalError):
        NFCeEmitHandler(backend).handle(message=_emit_directive(order), ctx={})
    assert backend.emit_calls == 0


def test_existing_access_key_is_noop(order):
    order.data["nfce_access_key"] = "existing"
    order.save(update_fields=["data"])
    backend = FakeBackend(emit_result=AUTHORIZED)

    NFCeEmitHandler(backend).handle(message=_emit_directive(order), ctx={})
    assert backend.emit_calls == 0


def test_processing_status_is_transient(order):
    backend = FakeBackend(emit_result=_error("focus_nfe_processing"))
    with pytest.raises(DirectiveTransientError):
        NFCeEmitHandler(backend).handle(message=_emit_directive(order), ctx={})


def _cancel_directive(order):
    return Directive.objects.create(
        topic="fiscal.cancel_nfce",
        payload={"order_ref": order.ref, "reason": "cancelamento de teste com justificativa"},
    )


def test_cancel_transport_error_is_transient(order):
    backend = FakeBackend(
        cancel_result=FiscalCancellationResult(
            success=False, error_code="focus_nfe_http_error", error_message="down"
        )
    )
    with pytest.raises(DirectiveTransientError):
        NFCeCancelHandler(backend).handle(message=_cancel_directive(order), ctx={})


def test_cancel_terminal_failure_alerts_operator(order):
    backend = FakeBackend(
        cancel_result=FiscalCancellationResult(
            success=False, error_code="focus_nfe_cancel_failed", error_message="fora da janela"
        )
    )
    with pytest.raises(DirectiveTerminalError):
        NFCeCancelHandler(backend).handle(message=_cancel_directive(order), ctx={})

    alert = OperatorAlert.objects.filter(type="fiscal_cancel_failed").first()
    assert alert is not None
    assert order.ref in alert.message
