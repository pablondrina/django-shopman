"""KDS command service tests."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from shopman.orderman.models import Order

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.backstage.services import kds
from shopman.backstage.services.exceptions import KDSError


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
def test_set_ticket_item_checked_is_idempotent(ticket, monkeypatch):
    core = Mock()
    monkeypatch.setattr(kds.kds_core, "toggle_ticket_item", core)

    result = kds.set_ticket_item_checked(ticket_pk=ticket.pk, index=0, checked=False, actor="kds:op")

    assert result.pk == ticket.pk
    core.assert_not_called()


@pytest.mark.django_db
def test_set_ticket_item_checked_delegates_only_when_state_changes(ticket, monkeypatch):
    core = Mock()
    monkeypatch.setattr(kds.kds_core, "toggle_ticket_item", core)

    result = kds.set_ticket_item_checked(ticket_pk=ticket.pk, index=0, checked=True, actor="kds:op")

    assert result.pk == ticket.pk
    core.assert_called_once_with(ticket, index=0, actor="kds:op")


@pytest.mark.django_db
def test_set_ticket_item_checked_raises_for_missing_item(ticket):
    with pytest.raises(KDSError):
        kds.set_ticket_item_checked(ticket_pk=ticket.pk, index=9, checked=True, actor="kds:op")


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


@pytest.mark.django_db
def test_expedition_action_idempotent_noops_for_completed_pickup_order(monkeypatch):
    order = Order.objects.create(ref="KDS-SVC-DONE", channel_ref="web", status=Order.Status.COMPLETED, total_q=1000)
    core = Mock()
    monkeypatch.setattr(kds.kds_core, "expedition_action_by_order_id", core)

    assert kds.expedition_action_idempotent(order_id=order.pk, action="complete", actor="kds:op") == Order.Status.COMPLETED
    core.assert_not_called()
