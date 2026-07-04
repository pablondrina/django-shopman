"""Estorno que falha NUNCA é silencioso — vira OperatorAlert crítico.

Regressão do gap P1: payment.refund engolia a exceção do gateway com só um
logger.warning, e o adapter reportando success=False era ignorado. Um PIX
capturado, cancelado e com estorno falho deixava o dinheiro do cliente retido
sem ninguém saber. Agora fail-loud, espelhando stock.fulfill.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import override_settings
from shopman.orderman.models import Order
from shopman.payman import PaymentService

from shopman.shop.models import Channel
from shopman.shop.services import payment as payment_service

pytestmark = pytest.mark.django_db

_MOCK_ADAPTERS = override_settings(
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_mock",
        "card": "shopman.shop.adapters.payment_mock",
        "cash": None,
        "external": None,
    }
)


@pytest.fixture
def paid_order(db):
    Channel.objects.create(ref="web", name="Web")
    PaymentService.create_intent("ORD-RF-1", 5000, "pix", gateway="mock", ref="INT-RF-1")
    PaymentService.authorize("INT-RF-1", gateway_id="gw-1")
    PaymentService.capture("INT-RF-1")
    return Order.objects.create(
        ref="ORD-RF-1",
        channel_ref="web",
        status=Order.Status.COMPLETED,
        total_q=5000,
        data={"payment": {"method": "pix", "intent_ref": "INT-RF-1"}},
    )


@_MOCK_ADAPTERS
def test_refund_transient_exception_queues_retry_not_immediate_alert(paid_order):
    """Falha transiente (gateway down): NÃO alerta já — enfileira retry assíncrono."""
    from shopman.orderman.models import Directive

    class FailingAdapter:
        def refund(self, *a, **k):
            raise RuntimeError("gateway down")

    with patch("shopman.shop.services.payment.get_adapter", return_value=FailingAdapter()):
        with patch("shopman.shop.services.observability.create_operator_alert") as alert:
            payment_service.refund(paid_order)

    alert.assert_not_called()  # transiente → retry, sem alarme falso
    assert Directive.objects.filter(topic="payment.refund", payload__order_ref="ORD-RF-1").exists()


@_MOCK_ADAPTERS
def test_refund_adapter_failure_result_raises_critical_alert(paid_order):
    class RejectingAdapter:
        def refund(self, *a, **k):
            return SimpleNamespace(success=False, message="declined", error_code="E_DECLINED")

    with patch("shopman.shop.services.payment.get_adapter", return_value=RejectingAdapter()):
        with patch("shopman.shop.services.observability.create_operator_alert") as alert:
            payment_service.refund(paid_order)

    alert.assert_called_once()
    assert alert.call_args.kwargs["type"] == "payment_refund_failed"


@_MOCK_ADAPTERS
def test_successful_refund_raises_no_alert(paid_order):
    with patch("shopman.shop.services.observability.create_operator_alert") as alert:
        payment_service.refund(paid_order)  # payment_mock estorna com sucesso

    alert.assert_not_called()


@_MOCK_ADAPTERS
def test_refund_handler_retries_then_alerts_on_exhaustion(paid_order):
    """O handler propaga DirectiveTransientError p/ retry; na última tentativa alerta."""
    from types import SimpleNamespace as NS

    from shopman.orderman.exceptions import DirectiveTransientError

    from shopman.shop.handlers.payment_refund import PaymentRefundHandler

    class FailingAdapter:
        def refund(self, *a, **k):
            raise RuntimeError("gateway down")

    handler = PaymentRefundHandler()
    payload = {"order_ref": "ORD-RF-1"}

    with patch("shopman.shop.services.payment.get_adapter", return_value=FailingAdapter()):
        # Tentativa 1 (attempts=1): propaga p/ retry, SEM alertar.
        with patch("shopman.shop.services.observability.create_operator_alert") as early:
            with pytest.raises(DirectiveTransientError):
                handler.handle(message=NS(payload=payload, attempts=1), ctx={})
        early.assert_not_called()

        # Última tentativa (attempts=5 == MAX): alerta antes de propagar.
        with patch("shopman.shop.services.observability.create_operator_alert") as last:
            with pytest.raises(DirectiveTransientError):
                handler.handle(message=NS(payload=payload, attempts=5), ctx={})
        last.assert_called_once()
        assert last.call_args.kwargs["type"] == "payment_refund_failed"
