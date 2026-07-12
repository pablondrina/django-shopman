"""reconcile_payments — resgate de webhook perdido e de PIX vencido.

* Intent capturada → dispatch("on_paid"), PULADO quando a fase já completou
  (marcador durável) — sem re-despachos em loop a cada ciclo.
* Intent PENDING vencida (Payman NÃO tem status "expired"; vencida = PENDING
  com expires_at no passado) → re-arma a directive payment.timeout, que cancela
  com segurança (verifica o gateway antes). Nunca cancela direto daqui.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone
from shopman.orderman.models import Directive, Order
from shopman.payman.models import PaymentIntent

pytestmark = pytest.mark.django_db


def _order(ref, *, status=Order.Status.NEW, data=None, age_minutes=180):
    o = Order.objects.create(
        ref=ref, channel_ref="web", status=status, total_q=1000, data=data or {}
    )
    old = timezone.now() - timedelta(minutes=age_minutes)
    Order.objects.filter(pk=o.pk).update(created_at=old)
    return o


def _run():
    call_command("reconcile_payments", stdout=StringIO())


def test_captured_intent_dispatches_on_paid():
    order = _order(
        "ORD-REC-PAID",
        data={"lifecycle": {"on_commit": "done"}, "payment": {"intent_ref": "PI-REC-1"}},
    )
    PaymentIntent.objects.create(
        ref="PI-REC-1",
        order_ref=order.ref,
        method=PaymentIntent.Method.PIX,
        status=PaymentIntent.Status.CAPTURED,
        amount_q=1000,
    )
    with patch("shopman.shop.lifecycle.dispatch") as dispatch:
        _run()
    dispatch.assert_called_once()
    assert dispatch.call_args.args[1] == "on_paid"


def test_captured_intent_skips_when_on_paid_already_complete():
    order = _order(
        "ORD-REC-DONE",
        data={
            "lifecycle": {"on_commit": "done", "on_paid": "done"},
            "payment": {"intent_ref": "PI-REC-2"},
        },
    )
    PaymentIntent.objects.create(
        ref="PI-REC-2",
        order_ref=order.ref,
        method=PaymentIntent.Method.PIX,
        status=PaymentIntent.Status.CAPTURED,
        amount_q=1000,
    )
    with patch("shopman.shop.lifecycle.dispatch") as dispatch:
        _run()
    dispatch.assert_not_called()


def test_expired_pending_intent_rearms_payment_timeout():
    order = _order(
        "ORD-REC-EXP",
        data={"lifecycle": {"on_commit": "done"}, "payment": {"intent_ref": "PI-REC-3"}},
    )
    PaymentIntent.objects.create(
        ref="PI-REC-3",
        order_ref=order.ref,
        method=PaymentIntent.Method.PIX,
        status=PaymentIntent.Status.PENDING,
        amount_q=1000,
        expires_at=timezone.now() - timedelta(hours=1),
    )

    with patch("shopman.shop.lifecycle.dispatch") as dispatch:
        _run()

    dispatch.assert_not_called()  # cancelar é papel do PaymentTimeoutHandler
    directive = Directive.objects.get(topic="payment.timeout", status="queued")
    assert directive.payload["order_ref"] == order.ref
    assert directive.payload["intent_ref"] == "PI-REC-3"
    order.refresh_from_db()
    assert order.status == Order.Status.NEW  # reconcile nunca cancela direto


def test_expired_pending_intent_with_live_timeout_directive_is_noop():
    order = _order(
        "ORD-REC-ARMED",
        data={"lifecycle": {"on_commit": "done"}, "payment": {"intent_ref": "PI-REC-4"}},
    )
    PaymentIntent.objects.create(
        ref="PI-REC-4",
        order_ref=order.ref,
        method=PaymentIntent.Method.PIX,
        status=PaymentIntent.Status.PENDING,
        amount_q=1000,
        expires_at=timezone.now() - timedelta(hours=1),
    )
    Directive.objects.create(
        topic="payment.timeout",
        payload={"order_ref": order.ref, "intent_ref": "PI-REC-4"},
        dedupe_key=f"payment.timeout:{order.ref}:PI-REC-4",
        status="queued",
    )

    _run()

    assert Directive.objects.filter(topic="payment.timeout").count() == 1


def test_pending_intent_not_yet_expired_is_noop():
    order = _order(
        "ORD-REC-WAIT",
        data={"lifecycle": {"on_commit": "done"}, "payment": {"intent_ref": "PI-REC-5"}},
    )
    PaymentIntent.objects.create(
        ref="PI-REC-5",
        order_ref=order.ref,
        method=PaymentIntent.Method.PIX,
        status=PaymentIntent.Status.PENDING,
        amount_q=1000,
        expires_at=timezone.now() + timedelta(hours=1),
    )
    with patch("shopman.shop.lifecycle.dispatch") as dispatch:
        _run()
    dispatch.assert_not_called()
    assert not Directive.objects.filter(topic="payment.timeout").exists()
