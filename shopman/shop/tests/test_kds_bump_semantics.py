"""Bump/recall do KDS: "ticket bumpado" ≠ "pedido avançou".

Regressões do audit pré-go-live:
- pedido de 2 estações: o bump do PRIMEIRO ticket persistia mas retornava
  False → a facade levantava KDSError → toast de erro + card fantasma em
  TODO pedido misto;
- recall com pedido READY criava ticket zumbi: reaberto mas impossível de
  concluir (guard exigia CONFIRMED/PREPARING antes de salvar);
- um ticket CANCELLED na sessão bloqueava o auto-READY para sempre.
"""

from __future__ import annotations

import pytest
from shopman.orderman.models import Order

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.shop.models import Channel
from shopman.shop.services import kds as kds_core

pytestmark = pytest.mark.django_db

SESSION_KEY = "sk-kds-bump-1"


@pytest.fixture
def order(db):
    Channel.objects.create(ref="pdv", name="PDV")
    return Order.objects.create(
        ref="ORD-KDS-BUMP",
        channel_ref="pdv",
        session_key=SESSION_KEY,
        status=Order.Status.PREPARING,
        total_q=1000,
    )


def _ticket(instance_ref: str, *, status: str = "pending") -> KDSTicket:
    instance, _ = KDSInstance.objects.get_or_create(
        ref=instance_ref, defaults={"name": instance_ref, "type": "prep"}
    )
    return KDSTicket.objects.create(
        session_key=SESSION_KEY,
        kds_instance=instance,
        status=status,
        items=[{"sku": "A", "name": "Item", "qty": 1, "checked": False}],
    )


def test_first_bump_of_multi_station_order_succeeds(order):
    t1 = _ticket("lanches")
    _ticket("cafes")

    # Bump do primeiro: ticket concluído, pedido segue PREPARING — SUCESSO.
    assert kds_core.complete_ticket(t1, actor="kds:op") is True
    t1.refresh_from_db()
    order.refresh_from_db()
    assert t1.status == "done"
    assert order.status == Order.Status.PREPARING


def test_last_bump_advances_order_to_ready(order):
    t1 = _ticket("lanches")
    t2 = _ticket("cafes")
    kds_core.complete_ticket(t1, actor="kds:op")

    assert kds_core.complete_ticket(t2, actor="kds:op") is True
    order.refresh_from_db()
    assert order.status == Order.Status.READY


def test_recall_then_rebump_works(order):
    ticket = _ticket("lanches")
    kds_core.complete_ticket(ticket, actor="kds:op")
    order.refresh_from_db()
    assert order.status == Order.Status.READY

    ticket.refresh_from_db()
    assert kds_core.reopen_ticket(ticket, actor="kds:op") is True
    order.refresh_from_db()
    # Recall puxa o pedido de volta ao preparo — expedição não o vê mais.
    assert order.status == Order.Status.PREPARING

    ticket.refresh_from_db()
    # E o re-bump conclui de novo — sem ticket zumbi.
    assert kds_core.complete_ticket(ticket, actor="kds:op") is True
    order.refresh_from_db()
    assert order.status == Order.Status.READY


def test_cancelled_ticket_does_not_block_ready(order):
    t1 = _ticket("lanches")
    _ticket("cafes", status="cancelled")

    assert kds_core.complete_ticket(t1, actor="kds:op") is True
    order.refresh_from_db()
    assert order.status == Order.Status.READY


def test_precommit_comanda_bump_succeeds_without_order(db):
    Channel.objects.create(ref="pdv", name="PDV")
    ticket = _ticket("lanches")  # session sem Order (comanda aberta)

    assert kds_core.complete_ticket(ticket, actor="kds:op") is True
    ticket.refresh_from_db()
    assert ticket.status == "done"


def _order_at(status: str, *, session_key: str, data: dict | None = None) -> Order:
    return Order.objects.create(
        ref=f"ORD-{session_key}",
        channel_ref="pdv",
        session_key=session_key,
        status=status,
        total_q=1000,
        data=data or {},
    )


def _ticket_for(session_key: str, *, status: str = "pending") -> KDSTicket:
    instance, _ = KDSInstance.objects.get_or_create(
        ref="lanches", defaults={"name": "lanches", "type": "prep"}
    )
    return KDSTicket.objects.create(
        session_key=session_key,
        kds_instance=instance,
        status=status,
        items=[{"sku": "A", "name": "Item", "qty": 1, "checked": False}],
    )


def test_bump_with_payment_gate_raises_with_real_reason(db):
    # "Não aberto" (False) e "gate de pagamento" NÃO são o mesmo estado: o
    # segundo levanta TicketCompletionBlocked com a razão real, para o operador
    # nunca ler "Ticket não está aberto" num ticket aberto.
    Channel.objects.create(ref="pdv", name="PDV")
    _order_at(
        Order.Status.CONFIRMED,
        session_key="sk-kds-gate",
        data={"payment": {"method": "pix"}},  # sem captura → gate fecha
    )
    ticket = _ticket_for("sk-kds-gate")

    with pytest.raises(kds_core.TicketCompletionBlocked, match="Pagamento ainda não foi confirmado"):
        kds_core.complete_ticket(ticket, actor="kds:op")
    ticket.refresh_from_db()
    assert ticket.status == "pending"  # bump não persistiu


def test_bump_of_unconfirmed_order_raises_with_real_reason(db):
    Channel.objects.create(ref="pdv", name="PDV")
    _order_at(Order.Status.NEW, session_key="sk-kds-new")
    ticket = _ticket_for("sk-kds-new")

    with pytest.raises(kds_core.TicketCompletionBlocked, match="não foi confirmado"):
        kds_core.complete_ticket(ticket, actor="kds:op")


def test_bump_of_closed_ticket_returns_false(order):
    ticket = _ticket("lanches", status="cancelled")

    assert kds_core.complete_ticket(ticket, actor="kds:op") is False


# ── Expedição por order_id: lock + replay idempotente + not-found ──────────


def test_expedition_by_order_id_completes_ready_pickup(db):
    Channel.objects.create(ref="pdv", name="PDV")
    order = _order_at(Order.Status.READY, session_key="sk-kds-exp-ready")

    assert kds_core.expedition_action_by_order_id(order.pk, action="complete", actor="kds:op") == Order.Status.COMPLETED
    order.refresh_from_db()
    assert order.status == Order.Status.COMPLETED


def test_expedition_by_order_id_replay_is_noop_success(db):
    # Replay (duas estações agindo no mesmo pedido) decidido SOB O LOCK:
    # pedido já no status alvo = sucesso no-op, nunca "Ação inválida".
    Channel.objects.create(ref="pdv", name="PDV")
    order = _order_at(Order.Status.COMPLETED, session_key="sk-kds-exp-replay")

    assert kds_core.expedition_action_by_order_id(order.pk, action="complete", actor="kds:op") == Order.Status.COMPLETED


def test_expedition_by_order_id_missing_order_raises_typed_not_found(db):
    with pytest.raises(kds_core.ExpeditionOrderNotFound):
        kds_core.expedition_action_by_order_id(999999, action="complete", actor="kds:op")
