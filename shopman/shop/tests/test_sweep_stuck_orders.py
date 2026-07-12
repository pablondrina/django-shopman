"""sweep_stuck_orders re-despacha fases de lifecycle perdidas por crash pós-commit.

O lifecycle roda em transaction.on_commit (não durável); um dispatch completo
grava order.data["lifecycle"][fase]="done" (DURABLE_PHASES). O sweeper acha
pedidos parados além do limiar SEM o marcador da fase do seu status e
re-despacha; pedido com fase completa é no-op.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone
from shopman.orderman.models import Order
from shopman.payman.models import PaymentIntent

pytestmark = pytest.mark.django_db


def _order(ref, *, status=Order.Status.NEW, data=None, age_minutes=30):
    o = Order.objects.create(
        ref=ref, channel_ref="web", status=status, total_q=1000, data=data or {}
    )
    if age_minutes:
        old = timezone.now() - timedelta(minutes=age_minutes)
        # bypassa auto_now_add/auto_now
        Order.objects.filter(pk=o.pk).update(created_at=old, updated_at=old)
    return o


def _sweep():
    with patch("shopman.shop.lifecycle.dispatch") as dispatch:
        call_command("sweep_stuck_orders")
    return dispatch


# ── on_commit (NEW) ──────────────────────────────────────────────────────────


def test_redispatches_orphan_new_without_marker():
    _order("ORD-ORPHAN", data={})
    dispatch = _sweep()
    dispatch.assert_called_once()
    assert dispatch.call_args.args[1] == "on_commit"


def test_skips_new_with_completed_marker():
    _order("ORD-DONE", data={"lifecycle": {"on_commit": "done"}})
    dispatch = _sweep()
    dispatch.assert_not_called()


def test_skips_young_order():
    _order("ORD-YOUNG", data={}, age_minutes=0)  # criado agora
    dispatch = _sweep()
    dispatch.assert_not_called()


def test_dry_run_does_not_dispatch():
    _order("ORD-DRY", data={})
    with patch("shopman.shop.lifecycle.dispatch") as dispatch:
        call_command("sweep_stuck_orders", "--dry-run")
    dispatch.assert_not_called()


# ── on_confirmed (CONFIRMED) ─────────────────────────────────────────────────


def test_redispatches_confirmed_without_marker():
    _order(
        "ORD-CONF-STUCK",
        status=Order.Status.CONFIRMED,
        data={"lifecycle": {"on_commit": "done"}},
    )
    dispatch = _sweep()
    dispatch.assert_called_once()
    assert dispatch.call_args.args[1] == "on_confirmed"


def test_skips_confirmed_with_completed_marker():
    _order(
        "ORD-CONF-OK",
        status=Order.Status.CONFIRMED,
        data={"lifecycle": {"on_commit": "done", "on_confirmed": "done"}},
    )
    dispatch = _sweep()
    dispatch.assert_not_called()


def test_order_is_swept_for_at_most_one_phase_per_cycle():
    # NEW sem NENHUM marcador e pago: só on_commit neste ciclo (ordem do
    # lifecycle); on_paid fica para o próximo ciclo, se ainda faltar.
    _order(
        "ORD-MULTI",
        data={"payment": {"intent_ref": "PI-MULTI", "captured_at": "2026-07-11T10:00:00"}},
    )
    dispatch = _sweep()
    dispatch.assert_called_once()
    assert dispatch.call_args.args[1] == "on_commit"


# ── on_paid (NEW/CONFIRMED pagos) ────────────────────────────────────────────


def test_redispatches_paid_order_without_marker_via_captured_at():
    # captured_at é gravado ANTES do dispatch em todos os caminhos de captura:
    # presença dele sem o marcador = crash entre o COMMIT e o fim do on_paid.
    _order(
        "ORD-PAID-STUCK",
        status=Order.Status.CONFIRMED,
        data={
            "lifecycle": {"on_commit": "done", "on_confirmed": "done"},
            "payment": {"intent_ref": "PI-STUCK", "captured_at": "2026-07-11T10:00:00"},
        },
    )
    dispatch = _sweep()
    dispatch.assert_called_once()
    assert dispatch.call_args.args[1] == "on_paid"


def test_redispatches_paid_order_via_payman_sufficient_capture():
    # Caminho Stripe: captura registrada só no Payman (sem captured_at no data).
    from shopman.payman import PaymentService

    order = _order(
        "ORD-PAID-PAYMAN",
        status=Order.Status.CONFIRMED,
        data={
            "lifecycle": {"on_commit": "done", "on_confirmed": "done"},
            "payment": {"intent_ref": "PI-PAYMAN", "method": "card"},
        },
    )
    PaymentService.create_intent(order.ref, 1000, "card", ref="PI-PAYMAN")
    PaymentService.authorize("PI-PAYMAN")
    PaymentService.capture("PI-PAYMAN")
    dispatch = _sweep()
    dispatch.assert_called_once()
    assert dispatch.call_args.args[1] == "on_paid"


def test_skips_paid_order_with_completed_marker():
    _order(
        "ORD-PAID-OK",
        status=Order.Status.CONFIRMED,
        data={
            "lifecycle": {"on_commit": "done", "on_confirmed": "done", "on_paid": "done"},
            "payment": {"intent_ref": "PI-OK", "captured_at": "2026-07-11T10:00:00"},
        },
    )
    dispatch = _sweep()
    dispatch.assert_not_called()


def test_skips_unpaid_order_for_on_paid():
    order = _order(
        "ORD-UNPAID",
        status=Order.Status.CONFIRMED,
        data={
            "lifecycle": {"on_commit": "done", "on_confirmed": "done"},
            "payment": {"intent_ref": "PI-PENDING-SWEEP", "method": "pix"},
        },
    )
    PaymentIntent.objects.create(
        ref="PI-PENDING-SWEEP",
        order_ref=order.ref,
        method=PaymentIntent.Method.PIX,
        status=PaymentIntent.Status.PENDING,
        amount_q=1000,
    )
    dispatch = _sweep()
    dispatch.assert_not_called()


# ── on_cancelled (CANCELLED) ─────────────────────────────────────────────────


def test_redispatches_cancelled_without_marker():
    _order(
        "ORD-CANC-STUCK",
        status=Order.Status.CANCELLED,
        data={"lifecycle": {"on_commit": "done"}},
    )
    dispatch = _sweep()
    dispatch.assert_called_once()
    assert dispatch.call_args.args[1] == "on_cancelled"


def test_skips_cancelled_with_completed_marker():
    _order(
        "ORD-CANC-OK",
        status=Order.Status.CANCELLED,
        data={"lifecycle": {"on_commit": "done", "on_cancelled": "done"}},
    )
    dispatch = _sweep()
    dispatch.assert_not_called()


# ── falha no re-dispatch alerta o operador ───────────────────────────────────


def test_failed_redispatch_creates_operator_alert():
    from shopman.backstage.models import OperatorAlert

    _order("ORD-BOOM", data={})
    with patch("shopman.shop.lifecycle.dispatch", side_effect=RuntimeError("boom")):
        call_command("sweep_stuck_orders")

    alert = OperatorAlert.objects.get(type="lifecycle_phase_stuck")
    assert alert.severity == "critical"
    assert "on_commit" in alert.message
    assert alert.order_ref == "ORD-BOOM"
