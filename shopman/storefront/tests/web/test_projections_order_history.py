"""Unit tests for shopman.shop.projections.order_history.

Uses customer/order fixtures from conftest.py. Verifies OrderHistoryProjection
shape, filter behaviour, status colour/label mapping, and graceful degradation.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from shopman.shop.projections.types import ORDER_STATUS_COLORS, OrderSummaryProjection
from shopman.storefront.projections.order_history import (
    FILTER_OPTIONS,
    OrderHistoryProjection,
    build_order_history,
)

pytestmark = pytest.mark.django_db


# ──────────────────────────────────────────────────────────────────────
# OrderHistoryProjection — shape
# ──────────────────────────────────────────────────────────────────────


class TestOrderHistoryShape:
    def test_returns_projection(self, customer):
        proj = build_order_history(customer)
        assert isinstance(proj, OrderHistoryProjection)

    def test_is_immutable(self, customer):
        proj = build_order_history(customer)
        with pytest.raises(FrozenInstanceError):
            proj.active_filter = "ativos"  # type: ignore[misc]

    def test_empty_orders_when_no_history(self, customer):
        proj = build_order_history(customer)
        assert proj.orders == ()
        assert proj.total_count == 0

    def test_phone_display(self, customer):
        proj = build_order_history(customer)
        assert proj.phone_display == customer.phone

    def test_filter_options_matches_constant(self, customer):
        proj = build_order_history(customer)
        assert proj.filter_options == FILTER_OPTIONS

    def test_default_filter_is_todos(self, customer):
        proj = build_order_history(customer)
        assert proj.active_filter == "todos"

    def test_unknown_filter_defaults_to_todos(self, customer):
        proj = build_order_history(customer, filter_param="invalid")
        assert proj.active_filter == "todos"


# ──────────────────────────────────────────────────────────────────────
# Orders — projection content
# ──────────────────────────────────────────────────────────────────────


class TestOrderHistoryOrders:
    def _make_order(self, customer, status="completed"):
        from shopman.orderman.models import Order

        return Order.objects.create(
            ref=f"ORD-{status.upper()[:3]}-TEST",
            channel_ref="web",
            status=status,
            total_q=2400,
            handle_type="phone",
            handle_ref=customer.phone,
            data={},
        )

    def test_order_appears_in_history(self, customer):
        self._make_order(customer)
        proj = build_order_history(customer)
        assert len(proj.orders) == 1
        assert proj.total_count == 1

    def test_order_summary_type(self, customer):
        self._make_order(customer)
        proj = build_order_history(customer)
        assert isinstance(proj.orders[0], OrderSummaryProjection)

    def test_order_ref(self, customer):
        order = self._make_order(customer, status="completed")
        proj = build_order_history(customer)
        assert proj.orders[0].ref == order.ref

    def test_total_display_formatted(self, customer):
        self._make_order(customer)
        proj = build_order_history(customer)
        assert proj.orders[0].total_display == "R$ 24,00"

    def test_status_label_pt(self, customer):
        self._make_order(customer, status="completed")
        proj = build_order_history(customer)
        assert proj.orders[0].status_label == "Concluído"

    def test_status_color_from_types(self, customer):
        self._make_order(customer, status="completed")
        proj = build_order_history(customer)
        assert proj.orders[0].status_color == ORDER_STATUS_COLORS["completed"]

    def test_created_at_display_formatted(self, customer):
        self._make_order(customer)
        proj = build_order_history(customer)
        assert "às" in proj.orders[0].created_at_display

    def test_item_count_zero_when_no_items(self, customer):
        self._make_order(customer)
        proj = build_order_history(customer)
        assert proj.orders[0].item_count == 0


# ──────────────────────────────────────────────────────────────────────
# Filters
# ──────────────────────────────────────────────────────────────────────


class TestOrderHistoryFilter:
    def _make_order(self, customer, status):
        from shopman.orderman.models import Order

        return Order.objects.create(
            ref=f"ORD-{status.upper()[:5]}",
            channel_ref="web",
            status=status,
            total_q=1000,
            handle_type="phone",
            handle_ref=customer.phone,
            data={},
        )

    def test_filter_todos_returns_all(self, customer):
        self._make_order(customer, "new")
        self._make_order(customer, "completed")
        proj = build_order_history(customer, filter_param="todos")
        assert len(proj.orders) == 2

    def test_filter_ativos_returns_only_active(self, customer):
        self._make_order(customer, "new")
        self._make_order(customer, "completed")
        proj = build_order_history(customer, filter_param="ativos")
        assert len(proj.orders) == 1
        assert proj.orders[0].status == "new"

    def test_filter_anteriores_excludes_active(self, customer):
        self._make_order(customer, "new")
        self._make_order(customer, "completed")
        proj = build_order_history(customer, filter_param="anteriores")
        assert len(proj.orders) == 1
        assert proj.orders[0].status == "completed"

    def test_active_filter_reflects_param(self, customer):
        proj = build_order_history(customer, filter_param="ativos")
        assert proj.active_filter == "ativos"
