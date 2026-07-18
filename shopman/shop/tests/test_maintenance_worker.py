"""maintenance_worker roda os "crons" do deployment em ciclo.

O worker é o coração operacional: resgata PIX pago com webhook perdido
(reconcile_payments), re-despacha pedido órfão em NEW (sweep_stuck_orders),
libera holds vencidos, limpa sessions/planejamento/D-1. Cobertura:

* cada tarefa do ciclo executa via ``--once`` e produz o efeito real esperado
  (cenários mínimos reais; só a fronteira ``lifecycle.dispatch`` é mockada,
  como em test_sweep_stuck_orders);
* exceção numa tarefa loga e NÃO derruba o ciclo nem impede as demais;
* o loop respeita ``--once`` (sem sleep) e o intervalo (floor de 30s).
"""

from __future__ import annotations

import contextlib
import logging
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import call, patch

import pytest
from django.core.management import call_command
from django.utils import timezone
from shopman.orderman.models import Order, Session
from shopman.payman.models import PaymentIntent
from shopman.stockman.models import Hold, HoldStatus, Move, Position, Quant

from shopman.shop.management.commands.maintenance_worker import MAINTENANCE_COMMANDS

pytestmark = pytest.mark.django_db

WORKER_LOGGER = "shopman.shop.management.commands.maintenance_worker"


@contextlib.contextmanager
def _capture_worker_logs(caplog, level=logging.ERROR):
    """Captura records do worker mesmo com ``propagate=False`` no logger ``shopman``.

    O ``caplog`` do pytest instala seu handler na raiz; o settings de produção põe
    ``propagate=False`` no logger ``shopman`` (config/settings.py), então os records
    do worker param antes da raiz e nunca chegam ao ``caplog``. Anexar o handler do
    ``caplog`` direto no logger do worker captura independente de propagação — vale
    igual local e no CI.
    """
    worker_logger = logging.getLogger(WORKER_LOGGER)
    with caplog.at_level(level, logger=WORKER_LOGGER):
        worker_logger.addHandler(caplog.handler)
        # Determinismo do count: com o handler do caplog anexado direto no logger
        # do worker, propagação ligada faria o MESMO record ser capturado de novo
        # pelo handler-raiz do caplog (record duplicado → count 2 em vez de 1). O
        # estado ambiente de propagate varia por ambiente/ordem (era flake de CI);
        # forçar False aqui garante captura única pelo handler direto, invariante.
        prev_propagate = worker_logger.propagate
        worker_logger.propagate = False
        try:
            yield
        finally:
            worker_logger.propagate = prev_propagate
            worker_logger.removeHandler(caplog.handler)


def _run_once():
    call_command("maintenance_worker", "--once", stdout=StringIO())


def _order(ref, *, status=Order.Status.NEW, data=None, age_minutes=30):
    o = Order.objects.create(
        ref=ref, channel_ref="web", status=status, total_q=1000, data=data or {}
    )
    if age_minutes:
        old = timezone.now() - timedelta(minutes=age_minutes)
        Order.objects.filter(pk=o.pk).update(created_at=old)  # bypassa auto_now_add
    return o


# ── (a) Cada tarefa do ciclo executa e produz o efeito esperado ──────────────


def test_cycle_releases_expired_holds():
    quant = Quant.objects.create(sku="PAO", _quantity=Decimal("5"))
    expired = Hold.objects.create(
        sku="PAO",
        quant=quant,
        quantity=Decimal("2"),
        target_date=date.today(),
        status=HoldStatus.PENDING,
        expires_at=timezone.now() - timedelta(minutes=5),
    )
    active = Hold.objects.create(
        sku="PAO",
        quant=quant,
        quantity=Decimal("1"),
        target_date=date.today(),
        status=HoldStatus.PENDING,
        expires_at=timezone.now() + timedelta(hours=1),
    )

    _run_once()

    expired.refresh_from_db()
    active.refresh_from_db()
    assert expired.status == HoldStatus.RELEASED
    assert expired.resolved_at is not None
    assert active.status == HoldStatus.PENDING


def test_cycle_removes_stale_sessions():
    stale = Session.objects.create(session_key="S-STALE", channel_ref="web")
    Session.objects.filter(pk=stale.pk).update(
        updated_at=timezone.now() - timedelta(hours=72)  # bypassa auto_now
    )
    fresh = Session.objects.create(session_key="S-FRESH", channel_ref="web")

    _run_once()

    assert not Session.objects.filter(pk=stale.pk).exists()
    assert Session.objects.filter(pk=fresh.pk).exists()


def test_cycle_removes_stale_planning_quants():
    yesterday = date.today() - timedelta(days=1)
    ghost = Quant.objects.create(sku="GHOST", target_date=yesterday, _quantity=Decimal("5"))
    planned = Quant.objects.create(
        sku="PLANNED", target_date=date.today() + timedelta(days=1), _quantity=Decimal("5")
    )

    _run_once()

    assert not Quant.objects.filter(pk=ghost.pk).exists()
    assert Quant.objects.filter(pk=planned.pk).exists()


def test_cycle_registers_expired_d1_stock_as_loss():
    ontem = Position.objects.create(ref="ontem", name="Ontem")
    quant = Quant.objects.create(sku="CROISSANT", position=ontem, _quantity=Decimal("0"))
    # Entrada D-1 de anteontem (Move.save soma o delta no cache do quant).
    Move.objects.create(
        quant=quant,
        delta=Decimal("3"),
        reason="d1:vitrine→ontem",
        timestamp=timezone.now() - timedelta(days=2),
    )

    _run_once()

    quant.refresh_from_db()
    assert quant._quantity == Decimal("0")
    waste = Move.objects.filter(quant=quant, kind=Move.Kind.WASTE)
    assert waste.count() == 1
    assert waste.get().reason.startswith("perda_d1_vencido:")


def test_cycle_rescues_paid_order_with_lost_webhook():
    # PIX capturado no Payman, mas o webhook nunca chegou: o pedido ficou em NEW.
    # O marcador on_commit=done mantém o sweep_stuck_orders fora do caminho —
    # aqui o resgate tem que vir do reconcile_payments.
    order = _order(
        "ORD-LOST-WEBHOOK",
        data={
            "lifecycle": {"on_commit": "done"},
            "payment": {"intent_ref": "PI-LOST"},
        },
        age_minutes=180,
    )
    PaymentIntent.objects.create(
        ref="PI-LOST",
        order_ref=order.ref,
        method=PaymentIntent.Method.PIX,
        status=PaymentIntent.Status.CAPTURED,
        amount_q=1000,
    )

    with patch("shopman.shop.lifecycle.dispatch") as dispatch:
        _run_once()

    dispatch.assert_called_once()
    dispatched_order, phase = dispatch.call_args.args
    assert dispatched_order.ref == order.ref
    assert phase == "on_paid"


def test_cycle_skips_order_with_pending_intent():
    order = _order(
        "ORD-STILL-PENDING",
        data={
            "lifecycle": {"on_commit": "done"},
            "payment": {"intent_ref": "PI-PENDING"},
        },
        age_minutes=180,
    )
    PaymentIntent.objects.create(
        ref="PI-PENDING",
        order_ref=order.ref,
        method=PaymentIntent.Method.PIX,
        status=PaymentIntent.Status.PENDING,
        amount_q=1000,
    )

    with patch("shopman.shop.lifecycle.dispatch") as dispatch:
        _run_once()

    dispatch.assert_not_called()
    order.refresh_from_db()
    assert order.status == Order.Status.NEW


def test_cycle_sweeps_stuck_new_order():
    # Órfão em NEW sem marcador (crash pós-commit); jovem demais para o
    # reconcile (cutoff 2h), velho o bastante para o sweeper (15 min).
    order = _order("ORD-ORPHAN", data={}, age_minutes=30)

    with patch("shopman.shop.lifecycle.dispatch") as dispatch:
        _run_once()

    dispatch.assert_called_once()
    dispatched_order, phase = dispatch.call_args.args
    assert dispatched_order.ref == order.ref
    assert phase == "on_commit"


# ── (b) Falha numa tarefa não derruba o ciclo ────────────────────────────────


def test_task_failure_logs_and_cycle_continues(caplog):
    # A PRIMEIRA tarefa do ciclo quebra de verdade (release_expired explode);
    # as demais ainda têm que rodar — a session stale abaixo deve sumir.
    stale = Session.objects.create(session_key="S-AFTER-FAILURE", channel_ref="web")
    Session.objects.filter(pk=stale.pk).update(
        updated_at=timezone.now() - timedelta(hours=72)
    )

    with (
        patch(
            "shopman.stockman.stock.release_expired",
            side_effect=RuntimeError("boom"),
        ),
        _capture_worker_logs(caplog),
    ):
        _run_once()

    assert not Session.objects.filter(pk=stale.pk).exists()
    # Robusto a ruído/duplicata de captura (a ordem de coleta de testes pode variar):
    # asserta o record ESPECÍFICO da falha esperada, não a contagem total de logs do
    # worker (que era frágil e flakava no CI).
    failures = [
        r
        for r in caplog.records
        if r.name == WORKER_LOGGER and "release_expired_holds" in r.getMessage()
    ]
    assert failures, "esperava um log de falha de release_expired_holds"
    assert "ciclo continua" in failures[0].getMessage()
    assert failures[0].exc_info is not None  # logger.exception preserva o traceback


def test_every_task_failing_still_completes_the_cycle(caplog):
    with (
        patch(
            "shopman.shop.management.commands.maintenance_worker.call_command",
            side_effect=RuntimeError("boom"),
        ) as cc,
        _capture_worker_logs(caplog),
    ):
        _run_once()

    assert cc.call_count == len(MAINTENANCE_COMMANDS)
    logged = [r.getMessage() for r in caplog.records if r.name == WORKER_LOGGER]
    # Cada comando que falhou tem que ter sido logado (o ciclo não para no 1º erro).
    # Presença por comando, não contagem total — imune a duplicata de captura / ruído
    # de ordem de coleta (o exato `== len` flakava no CI).
    for command in MAINTENANCE_COMMANDS:
        assert any(command in message for message in logged), f"faltou log de {command}"


# ── (c) Loop: --once, intervalo e floor ──────────────────────────────────────


class _StopLoop(Exception):
    """Escape determinístico do loop infinito nos testes (via time.sleep mockado)."""


def test_once_runs_one_cycle_in_order_and_never_sleeps():
    with (
        patch("shopman.shop.management.commands.maintenance_worker.call_command") as cc,
        patch("shopman.shop.management.commands.maintenance_worker.time.sleep") as sleep,
    ):
        _run_once()

    sleep.assert_not_called()
    assert cc.call_args_list == [
        call("release_expired_holds"),
        call("cleanup_stale_sessions"),
        call("sweep_orphan_holds"),
        call("cleanup_stale_planning"),
        call("cleanup_d1"),
        call("expire_broadcast_posts"),
        call("dispatch_scheduled_broadcasts"),
        call("reconcile_payments"),
        call("sweep_stuck_orders"),
        call("check_directive_health"),
    ]


def test_loop_sleeps_interval_between_cycles():
    # 1º ciclo → sleep(300) → 2º ciclo → sleep levanta _StopLoop (fim do teste).
    with (
        patch("shopman.shop.management.commands.maintenance_worker.call_command") as cc,
        patch(
            "shopman.shop.management.commands.maintenance_worker.time.sleep",
            side_effect=[None, _StopLoop()],
        ) as sleep,
        pytest.raises(_StopLoop),
    ):
        call_command("maintenance_worker", stdout=StringIO())

    assert cc.call_count == 2 * len(MAINTENANCE_COMMANDS)
    assert sleep.call_args_list == [call(300), call(300)]


@pytest.mark.parametrize(("requested", "effective"), [(5, 30), (60, 60)])
def test_interval_respects_floor_of_30_seconds(requested, effective):
    with (
        patch("shopman.shop.management.commands.maintenance_worker.call_command"),
        patch(
            "shopman.shop.management.commands.maintenance_worker.time.sleep",
            side_effect=_StopLoop(),
        ) as sleep,
        pytest.raises(_StopLoop),
    ):
        call_command("maintenance_worker", "--interval", str(requested), stdout=StringIO())

    sleep.assert_called_once_with(effective)
