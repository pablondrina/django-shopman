"""Higiene de holds órfãos — WP-B do AVAILABILITY-SALE-PRODUCTION-PLAN.

Holds planejados são INDEFINIDOS (``expires_at=None``, AVAILABILITY-PLAN §8):
nunca caem no ``release_expired``. Se a sessão dona morre sem liberar, eles
seguram o plano do dia para sempre (o "fantasma" do WP-A). Aqui fixamos os
três caminhos de liberação: morte explícita da sessão (``abandon_session``),
remoção por idade (``cleanup_stale_sessions``) e a varredura backstop
(``sweep_orphan_holds``).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone
from shopman.orderman.models import Session
from shopman.stockman.models import Hold
from shopman.stockman.models.enums import HoldStatus

from shopman.shop.models import Channel, Shop
from shopman.shop.services import sessions as session_service

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def shop_and_channel(db):
    Shop.objects.create(name="Test Shop", brand_name="Test")
    Channel.objects.create(ref="web", name="Loja Online")


def _open_session(session_key: str, *, handle_ref: str = "") -> Session:
    return Session.objects.create(
        session_key=session_key,
        channel_ref="web",
        state="open",
        handle_type="phone" if handle_ref else None,
        handle_ref=handle_ref or None,
        items=[],
        data={},
    )


def _planned_hold(reference: str, *, sku: str = "BAGUETE", target_date=None, **metadata) -> Hold:
    return Hold.objects.create(
        sku=sku,
        quant=None,
        quantity=Decimal("2"),
        target_date=target_date or timezone.localdate(),
        status=HoldStatus.PENDING,
        expires_at=None,
        metadata={"reference": reference, "planned": True, **metadata},
    )


def _is_released(hold: Hold) -> bool:
    hold.refresh_from_db()
    return hold.status == HoldStatus.RELEASED


# ── morte explícita da sessão ────────────────────────────────────────────────


def test_abandon_session_releases_holds():
    _open_session("SESS-ABANDONA")
    hold = _planned_hold("SESS-ABANDONA")

    assert session_service.abandon_session(session_key="SESS-ABANDONA", channel_ref="web")

    assert _is_released(hold), "abandonar a sessão tem que devolver as reservas dela"


def test_assign_phone_handle_releases_holds_of_abandoned_sessions():
    _open_session("SESS-ANTIGA", handle_ref="+5543999990001")
    ghost = _planned_hold("SESS-ANTIGA")
    _open_session("SESS-NOVA")
    keeper = _planned_hold("SESS-NOVA")

    session_service.assign_phone_handle(
        session_key="SESS-NOVA", channel_ref="web", phone="+5543999990001"
    )

    assert Session.objects.get(session_key="SESS-ANTIGA").state == "abandoned"
    assert _is_released(ghost), "sessão abandonada pelo handle deixou hold fantasma"
    assert not _is_released(keeper), "a sessão nova não pode perder a própria reserva"


# ── remoção por idade ────────────────────────────────────────────────────────


def test_cleanup_stale_sessions_releases_holds_before_delete():
    stale = _open_session("SESS-VELHA")
    Session.objects.filter(pk=stale.pk).update(
        updated_at=timezone.now() - timedelta(hours=72)
    )
    hold = _planned_hold("SESS-VELHA")

    call_command("cleanup_stale_sessions")

    assert not Session.objects.filter(session_key="SESS-VELHA").exists()
    assert _is_released(hold), (
        "deletar a Session sem liberar os holds cria órfãos irrastreáveis"
    )


# ── varredura backstop ───────────────────────────────────────────────────────


def test_sweep_releases_holds_of_dead_session_references():
    from shopman.backstage.models import OperatorAlert

    # Sem Session nenhuma (deletada fora do cleanup) e sessão committed.
    orphan_deleted = _planned_hold("SESS-SUMIU")
    committed = _open_session("SESS-COMMITTED")
    Session.objects.filter(pk=committed.pk).update(state="committed")
    orphan_committed = _planned_hold("SESS-COMMITTED")

    call_command("sweep_orphan_holds")

    assert _is_released(orphan_deleted)
    assert _is_released(orphan_committed), (
        "pós-commit os holds são re-tagueados ou liberados; sobrar referência "
        "de sessão committed é vazamento"
    )
    assert OperatorAlert.objects.filter(type="orphan_holds_released").exists(), (
        "devolver o plano do dia sem avisar o operador esconde a mudança de vitrine"
    )


def test_sweep_releases_holds_with_past_target_date():
    _open_session("SESS-ONTEM")
    yesterday = timezone.localdate() - timedelta(days=1)
    hold = _planned_hold("SESS-ONTEM", target_date=yesterday)

    call_command("sweep_orphan_holds")

    assert _is_released(hold), "a fornada de ontem já era — a reserva não promete nada"


def test_sweep_keeps_live_session_order_and_workorder_holds():
    _open_session("SESS-VIVA")
    live = _planned_hold("SESS-VIVA")
    order_owned = _planned_hold("order:WEB-123")
    production = _planned_hold("wo:WO-001", purpose="workorder")

    call_command("sweep_orphan_holds")

    assert not _is_released(live), "hold de sessão aberta não é órfão"
    assert not _is_released(order_owned), "hold adotado por pedido é do pedido"
    assert not _is_released(production), "reserva de produção não é da varredura"
