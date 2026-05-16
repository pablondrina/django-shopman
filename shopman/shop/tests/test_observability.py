"""Operational observability tests."""
from __future__ import annotations

import json
import logging

import pytest

from shopman.backstage.models import OperatorAlert
from shopman.shop.logging import JsonLogFormatter
from shopman.shop.services import observability


def test_json_log_formatter_includes_extra_fields() -> None:
    formatter = JsonLogFormatter()
    record = logging.LogRecord(
        name="shopman.operational",
        level=logging.INFO,
        pathname=__file__,
        lineno=12,
        msg="payment.reconciled",
        args=(),
        exc_info=None,
    )
    record.event = "payment.reconciled"
    record.order_ref = "ORD-OBS-1"
    record.amount_q = 1200

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "shopman.operational"
    assert payload["message"] == "payment.reconciled"
    assert payload["event"] == "payment.reconciled"
    assert payload["order_ref"] == "ORD-OBS-1"
    assert payload["amount_q"] == 1200
    assert "timestamp" in payload


@pytest.mark.django_db
def test_record_webhook_failure_creates_debounced_operator_alert() -> None:
    first = observability.record_webhook_failure(
        provider="stripe",
        reason="processing_failed",
        status_code=500,
        external_ref="evt_obs_1",
    )
    second = observability.record_webhook_failure(
        provider="stripe",
        reason="processing_failed",
        status_code=500,
        external_ref="evt_obs_1",
    )

    assert first is not None
    assert second is None
    alert = OperatorAlert.objects.get(type="webhook_failed")
    assert alert.severity == "error"
    assert "Webhook stripe falhou" in alert.message
    assert OperatorAlert.objects.filter(type="webhook_failed").count() == 1


@pytest.mark.django_db
def test_record_payment_reconciliation_failure_creates_critical_alert() -> None:
    alert = observability.record_payment_reconciliation_failure(
        gateway="stripe",
        intent_ref="PAY-OBS-1",
        order_ref="ORD-OBS-1",
        code="reconciliation_refund_mismatch",
        context={"local_refunded_q": 5000, "gateway_refunded_q": 3000},
    )

    assert alert is not None
    alert.refresh_from_db()
    assert alert.type == "payment_reconciliation_failed"
    assert alert.severity == "critical"
    assert alert.order_ref == "ORD-OBS-1"
    assert "PAY-OBS-1" in alert.message
