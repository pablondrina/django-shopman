"""Timeout de PIX consulta o gateway antes de cancelar (webhook perdido ≠ não pago).

Regressão do audit pré-go-live: um webhook EFI perdido deixava o pedido "não
pago" localmente; o timeout então CANCELAVA um pedido com dinheiro capturado no
gateway, sem refund. Agora o auto-cancel só acontece com resposta definitiva do
gateway de que não há pagamento; estado incerto adia a decisão.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.models import Channel
from shopman.shop.services import payment as payment_service
from shopman.shop.services.customer_orders import resolve_payment_timeout_if_due

pytestmark = pytest.mark.django_db


@pytest.fixture
def overdue_pix_order(db):
    from shopman.payman import PaymentService

    Channel.objects.create(ref="web", name="Web")
    PaymentService.create_intent(
        "ORD-PIX-TIMEOUT", 5000, "pix", gateway="efi", ref="INT-PIX-1"
    )
    expired = (timezone.now() - timedelta(minutes=5)).isoformat()
    return Order.objects.create(
        ref="ORD-PIX-TIMEOUT",
        channel_ref="web",
        status=Order.Status.NEW,
        total_q=5000,
        data={
            "fulfillment_type": "pickup",
            "payment": {
                "method": "pix",
                "intent_ref": "INT-PIX-1",
                "expires_at": expired,
            },
        },
    )


def _stub_adapter(capture_result):
    return SimpleNamespace(capture=lambda intent_ref: capture_result)


def test_gateway_paid_blocks_cancel_and_promotes_order(overdue_pix_order):
    paid = SimpleNamespace(success=True, transaction_id="txid-1", amount_q=5000, error_code="")
    with patch.object(payment_service, "get_adapter", return_value=_stub_adapter(paid)):
        cancelled = resolve_payment_timeout_if_due(overdue_pix_order)

    assert cancelled is False
    overdue_pix_order.refresh_from_db()
    assert overdue_pix_order.status != Order.Status.CANCELLED
    assert overdue_pix_order.data["payment"]["captured_at"]


def test_gateway_unreachable_defers_cancel(overdue_pix_order):
    error = SimpleNamespace(success=False, transaction_id="", amount_q=0, error_code="error")
    with patch.object(payment_service, "get_adapter", return_value=_stub_adapter(error)):
        cancelled = resolve_payment_timeout_if_due(overdue_pix_order)

    assert cancelled is False
    overdue_pix_order.refresh_from_db()
    assert overdue_pix_order.status == Order.Status.NEW  # decisão adiada, não cancelado


def test_gateway_confirms_unpaid_allows_cancel(overdue_pix_order):
    unpaid = SimpleNamespace(success=False, transaction_id="", amount_q=0, error_code="ativa")
    with patch.object(payment_service, "get_adapter", return_value=_stub_adapter(unpaid)):
        cancelled = resolve_payment_timeout_if_due(overdue_pix_order)

    assert cancelled is True
    overdue_pix_order.refresh_from_db()
    assert overdue_pix_order.status == Order.Status.CANCELLED


def test_paid_promotion_dispatches_on_paid_once_under_double_resolve(overdue_pix_order):
    """Dois resolvers concorrentes veem 'paid' mas on_paid dispara UMA vez
    (lock + re-check de captured_at)."""
    from unittest.mock import patch

    paid = SimpleNamespace(success=True, transaction_id="txid-1", amount_q=5000, error_code="")
    calls = []
    with patch.object(payment_service, "get_adapter", return_value=_stub_adapter(paid)), \
         patch("shopman.shop.lifecycle.dispatch", side_effect=lambda o, p: calls.append(p)):
        s1 = payment_service.verify_gateway_before_timeout_cancel(overdue_pix_order)
        # Segundo resolver, mesmo pedido, já promovido.
        overdue_pix_order.refresh_from_db()
        s2 = payment_service.verify_gateway_before_timeout_cancel(overdue_pix_order)

    assert s1 == "paid" and s2 == "paid"
    assert calls.count("on_paid") == 1  # nunca duplica
