from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Directive, IdempotencyKey, Order
from shopman.payman.models import PaymentIntent, PaymentTransaction

from shopman.shop.models import Channel


def _diagnosis_text(diagnosis) -> str:
    return "\n".join(f"{line.level} {line.name} {line.detail}" for line in diagnosis.lines)


@pytest.mark.django_db
def test_worker_diagnostic_flags_stuck_and_failed_without_payload_data():
    from scripts.diagnose_operational import diagnose_worker

    now = timezone.now()
    Directive.objects.create(
        topic="notify.customer",
        status=Directive.Status.RUNNING,
        payload={"phone": "+5543999001122", "secret": "do-not-print"},
        attempts=3,
        started_at=now - timedelta(minutes=15),
        last_error="gateway timeout for +5543999001122",
        error_code="transient",
    )
    Directive.objects.create(
        topic="stock.release",
        status=Directive.Status.FAILED,
        payload={"token": "do-not-print"},
        attempts=5,
        last_error="token=abc123 failed",
        error_code="terminal",
    )

    diagnosis = diagnose_worker(limit=5)
    text = _diagnosis_text(diagnosis)

    assert diagnosis.exit_code == 1
    assert "stuck directive" in text
    assert "failed directive" in text
    assert "+5543999001122" not in text
    assert "do-not-print" not in text
    assert "abc123" not in text


@pytest.mark.django_db
def test_payments_diagnostic_flags_captured_cancelled_order_without_payload_data():
    from scripts.diagnose_operational import diagnose_payments

    channel = Channel.objects.create(ref="diag", name="Diagnostico")
    order = Order.objects.create(
        ref="DIAG-PAY-001",
        channel_ref=channel.ref,
        status=Order.Status.CANCELLED,
        total_q=1200,
        data={
            "payment": {"intent_ref": "PAY-DIAG-001"},
            "customer_phone": "+5543999001122",
        },
    )
    intent = PaymentIntent.objects.create(
        ref="PAY-DIAG-001",
        order_ref=order.ref,
        method=PaymentIntent.Method.PIX,
        status=PaymentIntent.Status.CAPTURED,
        amount_q=1200,
        gateway="efi",
    )
    PaymentTransaction.objects.create(
        intent=intent,
        type=PaymentTransaction.Type.CAPTURE,
        amount_q=1200,
    )

    diagnosis = diagnose_payments(limit=5)
    text = _diagnosis_text(diagnosis)

    assert diagnosis.exit_code == 1
    assert "payment divergence" in text
    assert "DIAG-PAY-001" in text
    assert "+5543999001122" not in text
    assert "customer_phone" not in text


@pytest.mark.django_db
def test_webhook_diagnostic_redacts_idempotency_keys():
    from scripts.diagnose_operational import diagnose_webhooks

    key = IdempotencyKey.objects.create(
        scope="webhook:efi-pix",
        key="raw-provider-secret-event-id",
        status="in_progress",
    )
    IdempotencyKey.objects.filter(pk=key.pk).update(created_at=timezone.now() - timedelta(minutes=10))

    diagnosis = diagnose_webhooks(limit=5)
    text = _diagnosis_text(diagnosis)

    assert diagnosis.exit_code == 1
    assert "sha256:" in text
    assert "raw-provider-secret-event-id" not in text
