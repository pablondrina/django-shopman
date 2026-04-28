"""KDS command service tests."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.backstage.services import kds
from shopman.backstage.services.exceptions import KDSError
from shopman.orderman.models import Order


@pytest.fixture
def ticket(db):
    order = Order.objects.create(ref="KDS-SVC-1", channel_ref="web", total_q=1000)
    instance = KDSInstance.objects.create(ref="prep-svc", name="Preparo", type="prep")
    return KDSTicket.objects.create(
        order=order,
        kds_instance=instance,
        items=[{"sku": "A", "name": "Item", "qty": 1, "checked": False}],
    )


@pytest.mark.django_db
def test_check_ticket_item_delegates_to_core(ticket, monkeypatch):
    core = Mock()
    monkeypatch.setattr(kds.kds_core, "toggle_ticket_item", core)

    result = kds.check_ticket_item(ticket_pk=ticket.pk, index=0, actor="kds:op")

    assert result.pk == ticket.pk
    core.assert_called_once_with(ticket, index=0, actor="kds:op")


@pytest.mark.django_db
def test_check_ticket_item_raises_for_missing_ticket():
    with pytest.raises(KDSError):
        kds.check_ticket_item(ticket_pk=999999, index=0, actor="kds:op")


@pytest.mark.django_db
def test_mark_ticket_done_delegates_to_core(ticket, monkeypatch):
    core = Mock()
    monkeypatch.setattr(kds.kds_core, "complete_ticket", core)

    result = kds.mark_ticket_done(ticket_pk=ticket.pk, actor="kds:op")

    assert result.pk == ticket.pk
    core.assert_called_once_with(ticket, actor="kds:op")


@pytest.mark.django_db
def test_mark_ticket_done_raises_for_missing_ticket():
    with pytest.raises(KDSError):
        kds.mark_ticket_done(ticket_pk=999999, actor="kds:op")


def test_expedition_action_wraps_invalid_action(monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("bad")

    monkeypatch.setattr(kds.kds_core, "expedition_action_by_order_id", fail)

    with pytest.raises(KDSError):
        kds.expedition_action(order_id=1, action="bad", actor="kds:op")


def test_expedition_action_delegates_to_core(monkeypatch):
    core = Mock(return_value="ok")
    monkeypatch.setattr(kds.kds_core, "expedition_action_by_order_id", core)

    assert kds.expedition_action(order_id=1, action="dispatch", actor="kds:op") == "ok"
    core.assert_called_once_with(1, action="dispatch", actor="kds:op")
