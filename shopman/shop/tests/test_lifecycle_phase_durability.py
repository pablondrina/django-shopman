"""Marcador durável de fase do lifecycle (DURABLE_PHASES).

dispatch() grava order.data["lifecycle"][fase]="done" APÓS o handler retornar.
Handler que levanta não marca — e o sweep_stuck_orders re-despacha. O marcador
sobrevive a dispatch aninhado (merge com o data fresco do banco).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from shopman.orderman.models import Order

from shopman.shop import lifecycle

pytestmark = pytest.mark.django_db


def _order(ref, *, status=Order.Status.NEW, data=None):
    return Order.objects.create(
        ref=ref, channel_ref="web", status=status, total_q=1000, data=data or {}
    )


def test_dispatch_marks_durable_phase_on_success():
    order = _order("ORD-MARK-CANC", status=Order.Status.CANCELLED)
    lifecycle.dispatch(order, "on_cancelled")
    order.refresh_from_db()
    assert order.data["lifecycle"]["on_cancelled"] == "done"
    assert lifecycle.phase_complete(order, "on_cancelled")


def test_dispatch_marks_on_confirmed():
    order = _order("ORD-MARK-CONF", status=Order.Status.CONFIRMED)
    lifecycle.dispatch(order, "on_confirmed")
    order.refresh_from_db()
    assert order.data["lifecycle"]["on_confirmed"] == "done"


def test_non_durable_phase_is_not_marked():
    order = _order("ORD-MARK-PREP", status=Order.Status.PREPARING)
    lifecycle.dispatch(order, "on_preparing")
    order.refresh_from_db()
    assert "on_preparing" not in (order.data.get("lifecycle") or {})


def test_handler_crash_leaves_phase_unmarked():
    order = _order("ORD-CRASH", status=Order.Status.CANCELLED)
    with (
        patch("shopman.shop.lifecycle.stock.release", side_effect=RuntimeError("boom")),
        pytest.raises(RuntimeError),
    ):
        lifecycle.dispatch(order, "on_cancelled")
    order.refresh_from_db()
    assert not lifecycle.phase_complete(order, "on_cancelled")


def test_crash_between_transition_and_phase_is_rescued_by_sweeper(
    django_capture_on_commit_callbacks,
):
    """Crash simulado entre o COMMIT da transição e o fim do _on_confirmed.

    A transição para CONFIRMED persiste; o handler morre no meio; o marcador
    não existe. O sweeper detecta e re-despacha a fase — que aí completa e
    ganha o marcador.
    """
    from datetime import timedelta

    from django.core.management import call_command
    from django.utils import timezone

    order = _order(
        "ORD-CRASH-CONF",
        data={
            "lifecycle": {"on_commit": "done"},
            "availability_decision": {"approved": True, "decisions": [{"sku": "PAO"}]},
        },
    )

    with (
        patch("shopman.shop.lifecycle.notification.send", side_effect=RuntimeError("deploy!")),
        pytest.raises(RuntimeError),
        django_capture_on_commit_callbacks(execute=True),
    ):
        order.transition_status(Order.Status.CONFIRMED, actor="operator:test")

    order.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED  # transição commitou
    assert not lifecycle.phase_complete(order, "on_confirmed")  # fase perdida

    # Envelhece além do limiar e deixa o sweeper resgatar (agora sem crash).
    Order.objects.filter(pk=order.pk).update(
        updated_at=timezone.now() - timedelta(minutes=30)
    )
    order.refresh_from_db()
    call_command("sweep_stuck_orders")

    order.refresh_from_db()
    assert lifecycle.phase_complete(order, "on_confirmed")


def test_mark_phase_complete_merges_with_fresh_db_data():
    # Instance com data desatualizado não pode apagar marcador gravado por
    # um dispatch aninhado nesse meio-tempo.
    order = _order("ORD-MERGE", status=Order.Status.CONFIRMED)
    Order.objects.filter(pk=order.pk).update(
        data={"lifecycle": {"on_confirmed": "done"}, "hold_ids": []}
    )
    # order (em memória) ainda tem data={} — stale.
    lifecycle._mark_phase_complete(order, "on_paid")
    order.refresh_from_db()
    assert order.data["lifecycle"] == {"on_confirmed": "done", "on_paid": "done"}
    assert order.data["hold_ids"] == []
