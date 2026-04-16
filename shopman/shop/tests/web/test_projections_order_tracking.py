"""Unit tests for shopman.shop.projections.order_tracking.

Uses order fixtures from conftest.py. Verifies OrderTrackingProjection
and OrderTrackingStatusProjection shape, timeline construction, terminal
status detection, fulfillment display, and the status colour mapping.
"""
from __future__ import annotations

import pytest

from shopman.shop.projections.order_tracking import (
    OrderTrackingProjection,
    OrderTrackingStatusProjection,
    build_order_tracking,
    build_order_tracking_status,
)
from shopman.shop.projections.types import (
    ORDER_STATUS_COLORS,
    FulfillmentProjection,
    OrderItemProjection,
    TimelineEventProjection,
)

pytestmark = pytest.mark.django_db


# ──────────────────────────────────────────────────────────────────────
# OrderTrackingProjection — shape
# ──────────────────────────────────────────────────────────────────────


class TestOrderTrackingShape:
    def test_returns_projection(self, order):
        proj = build_order_tracking(order)
        assert isinstance(proj, OrderTrackingProjection)

    def test_is_immutable(self, order):
        from dataclasses import FrozenInstanceError

        proj = build_order_tracking(order)
        with pytest.raises(FrozenInstanceError):
            proj.status = "confirmed"  # type: ignore[misc]

    def test_order_ref_matches(self, order):
        proj = build_order_tracking(order)
        assert proj.order_ref == order.ref

    def test_status_matches(self, order):
        proj = build_order_tracking(order)
        assert proj.status == "new"
        assert proj.status_label == "Recebido"

    def test_total_display_formatted(self, order):
        proj = build_order_tracking(order)
        assert proj.total_display.startswith("R$ ")
        assert "16,00" in proj.total_display  # 1600q

    def test_is_active_for_non_terminal(self, order):
        proj = build_order_tracking(order)
        assert proj.is_active is True

    def test_is_active_false_for_completed(self, order):
        from shopman.orderman.models import Order as OrdOrder

        OrdOrder.objects.filter(pk=order.pk).update(status="completed")
        order.refresh_from_db()
        proj = build_order_tracking(order)
        assert proj.is_active is False


# ──────────────────────────────────────────────────────────────────────
# Items
# ──────────────────────────────────────────────────────────────────────


class TestOrderTrackingItems:
    def test_items_populated(self, order_items):
        proj = build_order_tracking(order_items)
        assert len(proj.items) == 2
        assert all(isinstance(i, OrderItemProjection) for i in proj.items)

    def test_item_fields(self, order_items, product, croissant):
        proj = build_order_tracking(order_items)
        skus = {i.sku for i in proj.items}
        assert product.sku in skus
        assert croissant.sku in skus

    def test_item_price_formatted(self, order_items):
        proj = build_order_tracking(order_items)
        for item in proj.items:
            assert item.unit_price_display.startswith("R$ ")
            assert item.total_display.startswith("R$ ")
            assert item.qty > 0

    def test_empty_order_has_empty_items(self, order):
        proj = build_order_tracking(order)
        assert proj.items == ()


# ──────────────────────────────────────────────────────────────────────
# Timeline
# ──────────────────────────────────────────────────────────────────────


class TestOrderTrackingTimeline:
    def test_created_event_in_timeline(self, order):
        # Emit a created event
        order.emit_event(event_type="created", actor="test", payload={})
        proj = build_order_tracking(order)
        assert len(proj.timeline) >= 1
        assert all(isinstance(e, TimelineEventProjection) for e in proj.timeline)
        labels = [e.label for e in proj.timeline]
        assert "Pedido criado" in labels

    def test_status_change_appears_in_timeline(self, order):
        order.emit_event(
            event_type="status_changed",
            actor="test",
            payload={"new_status": "confirmed"},
        )
        proj = build_order_tracking(order)
        labels = [e.label for e in proj.timeline]
        assert "Confirmado" in labels

    def test_timeline_timestamp_display_formatted(self, order):
        order.emit_event(event_type="created", actor="test", payload={})
        proj = build_order_tracking(order)
        for event in proj.timeline:
            assert event.timestamp_display  # non-empty
            assert "às" in event.timestamp_display  # e.g. "15/04 às 14:32"

    def test_timeline_is_immutable(self, order):
        from dataclasses import FrozenInstanceError

        order.emit_event(event_type="created", actor="test", payload={})
        proj = build_order_tracking(order)
        with pytest.raises(FrozenInstanceError):
            proj.timeline[0].label = "changed"  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────────────
# Status colours (Penguin tokens)
# ──────────────────────────────────────────────────────────────────────


class TestStatusColours:
    @pytest.mark.parametrize("status,expected_fragment", [
        ("new", "info"),
        ("confirmed", "info"),
        ("preparing", "warning"),
        ("ready", "success"),
        ("dispatched", "info"),
        ("delivered", "success"),
        ("completed", "success"),
        ("cancelled", "danger"),
    ])
    def test_status_colour_uses_penguin_tokens(self, order, status, expected_fragment):
        from shopman.orderman.models import Order as OrdOrder

        OrdOrder.objects.filter(pk=order.pk).update(status=status)
        order.refresh_from_db()
        proj = build_order_tracking(order)
        assert expected_fragment in proj.status_color

    def test_ready_pickup_label(self, order):
        from shopman.orderman.models import Order as OrdOrder

        OrdOrder.objects.filter(pk=order.pk).update(status="ready", data={"fulfillment_type": "pickup"})
        order.refresh_from_db()
        proj = build_order_tracking(order)
        assert proj.status_label == "Pronto para retirada"

    def test_ready_delivery_label(self, order):
        from shopman.orderman.models import Order as OrdOrder

        OrdOrder.objects.filter(pk=order.pk).update(status="ready", data={"fulfillment_type": "delivery"})
        order.refresh_from_db()
        proj = build_order_tracking(order)
        assert proj.status_label == "Aguardando motoboy"


# ──────────────────────────────────────────────────────────────────────
# OrderTrackingStatusProjection
# ──────────────────────────────────────────────────────────────────────


class TestOrderTrackingStatusProjection:
    def test_returns_status_projection(self, order):
        proj = build_order_tracking_status(order)
        assert isinstance(proj, OrderTrackingStatusProjection)

    def test_is_immutable(self, order):
        from dataclasses import FrozenInstanceError

        proj = build_order_tracking_status(order)
        with pytest.raises(FrozenInstanceError):
            proj.status = "confirmed"  # type: ignore[misc]

    def test_not_terminal_for_active_order(self, order):
        proj = build_order_tracking_status(order)
        assert proj.is_terminal is False

    @pytest.mark.parametrize("status", ["completed", "cancelled", "returned"])
    def test_terminal_for_terminal_statuses(self, order, status):
        from shopman.orderman.models import Order as OrdOrder

        OrdOrder.objects.filter(pk=order.pk).update(status=status)
        order.refresh_from_db()
        proj = build_order_tracking_status(order)
        assert proj.is_terminal is True

    def test_status_label_and_color_populated(self, order):
        proj = build_order_tracking_status(order)
        assert proj.status_label
        assert proj.status_color

    def test_can_cancel_false_without_payment_service(self, order):
        # can_cancel degrades gracefully
        proj = build_order_tracking_status(order)
        assert isinstance(proj.can_cancel, bool)
