"""Estorno é idempotente ponta a ponta (gateway determinístico + Payman dedup).

Regressão do code-review max-effort: devolução PARCIAL executada duas vezes num
retry (a flag refund_processed era salva fora da transação do refund, e o saldo
reembolsável parcial não zera). Agora um retry reapresenta a MESMA devolução
(dev_id/idempotency_key determinístico) e o Payman deduplica por gateway_id.
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from shopman.orderman.models import Order
from shopman.payman import PaymentService
from shopman.payman.models import PaymentTransaction

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
    PaymentService.create_intent("ORD-REFUND-1", 5000, "pix", gateway="mock", ref="INT-REFUND-1")
    PaymentService.authorize("INT-REFUND-1", gateway_id="gw-1")
    PaymentService.capture("INT-REFUND-1")
    return Order.objects.create(
        ref="ORD-REFUND-1",
        channel_ref="web",
        status=Order.Status.COMPLETED,
        total_q=5000,
        data={"payment": {"method": "pix", "intent_ref": "INT-REFUND-1"}},
    )


def _refund_txns():
    return PaymentTransaction.objects.filter(
        intent__ref="INT-REFUND-1", type=PaymentTransaction.Type.REFUND
    )


@_MOCK_ADAPTERS
def test_partial_refund_retry_does_not_double_refund(paid_order):
    key = "return:ORD-REFUND-1:0"
    # 1ª execução: estorna 2000 (parcial).
    payment_service.refund(paid_order, amount_q=2000, idempotency_key=key)
    # Retry (mesma chave) após um "crash": NÃO pode estornar de novo.
    payment_service.refund(paid_order, amount_q=2000, idempotency_key=key)

    txns = _refund_txns()
    assert txns.count() == 1
    assert txns.first().amount_q == 2000
    assert PaymentService.refunded_total("INT-REFUND-1") == 2000


@_MOCK_ADAPTERS
def test_distinct_partial_returns_each_refund_once(paid_order):
    # Duas devoluções parciais DISTINTAS (índices diferentes) somam.
    payment_service.refund(paid_order, amount_q=1500, idempotency_key="return:ORD-REFUND-1:0")
    payment_service.refund(paid_order, amount_q=1000, idempotency_key="return:ORD-REFUND-1:1")

    assert _refund_txns().count() == 2
    assert PaymentService.refunded_total("INT-REFUND-1") == 2500
