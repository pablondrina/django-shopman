"""Order command service facade tests."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from shopman.backstage.services import orders
from shopman.backstage.services.exceptions import OrderError


def test_find_order_delegates(monkeypatch):
    core = Mock(return_value="order")
    monkeypatch.setattr(orders.operator_orders, "find_order", core)

    assert orders.find_order("ABC") == "order"
    core.assert_called_once_with("ABC")


def test_confirm_order_delegates(monkeypatch):
    core = Mock()
    monkeypatch.setattr(orders.operator_orders, "confirm_order", core)

    orders.confirm_order("order", actor="operator:ana")

    core.assert_called_once_with("order", actor="operator:ana")


def test_reject_order_validates_reason(monkeypatch):
    core = Mock()
    monkeypatch.setattr(orders.operator_orders, "reject_order", core)

    with pytest.raises(OrderError):
        orders.reject_order("order", reason="", actor="operator:ana", rejected_by="ana")

    orders.reject_order("order", reason=" sem estoque ", actor="operator:ana", rejected_by="ana")
    core.assert_called_once_with(
        "order",
        reason="sem estoque",
        actor="operator:ana",
        rejected_by="ana",
    )


def test_advance_order_wraps_value_error(monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("bad")

    monkeypatch.setattr(orders.operator_orders, "advance_order", fail)

    with pytest.raises(OrderError):
        orders.advance_order("order", actor="operator:ana")


def test_mark_paid_save_notes_and_history_delegate(monkeypatch):
    mark_paid = Mock(return_value=True)
    save_notes = Mock()
    recent = Mock(return_value=["order"])
    monkeypatch.setattr(orders.operator_orders, "mark_paid", mark_paid)
    monkeypatch.setattr(orders.operator_orders, "save_internal_notes", save_notes)
    monkeypatch.setattr(orders.operator_orders, "recent_history", recent)

    assert orders.mark_paid("order", actor="operator:ana", operator_username="ana") is True
    orders.save_internal_notes("order", notes="obs")
    assert orders.recent_history(limit=5) == ["order"]

    mark_paid.assert_called_once_with("order", actor="operator:ana", operator_username="ana")
    save_notes.assert_called_once_with("order", notes="obs")
    recent.assert_called_once_with(limit=5)
