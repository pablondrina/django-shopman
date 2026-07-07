"""Order mutation service facade tests."""

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
        cancellation_code="",
    )


def test_advance_order_surfaces_specific_reason(monkeypatch):
    # advance_order must surface the operator-facing reason (advance_block_reason),
    # not swallow it into a generic "Ação inválida".
    def fail(*args, **kwargs):
        raise ValueError("Pagamento ainda não foi confirmado. Aguarde antes de iniciar o preparo.")

    monkeypatch.setattr(orders.operator_orders, "advance_order", fail)

    with pytest.raises(OrderError) as exc_info:
        orders.advance_order("order", actor="operator:ana")
    assert "Pagamento ainda não foi confirmado" in str(exc_info.value)


def test_save_notes_and_history_delegate(monkeypatch):
    save_notes = Mock()
    recent = Mock(return_value=["order"])
    monkeypatch.setattr(orders.operator_orders, "save_kitchen_note", save_notes)
    monkeypatch.setattr(orders.operator_orders, "recent_history", recent)

    orders.save_kitchen_note("order", notes="obs")
    assert orders.recent_history(limit=5) == ["order"]

    save_notes.assert_called_once_with("order", notes="obs")
    recent.assert_called_once_with(limit=5)


def test_cancel_order_delegates(monkeypatch):
    cancel_order = Mock()
    monkeypatch.setattr(orders.operator_orders, "cancel_order", cancel_order)

    orders.cancel_order(
        "order", reason="cliente pediu", actor="admin:ana", customer_note="cliente pediu"
    )

    cancel_order.assert_called_once_with(
        "order",
        reason="cliente pediu",
        actor="admin:ana",
        cancellation_code="",
        customer_note="cliente pediu",
    )
