"""
WP-ST6: E2E lifecycle tests for Order status flows.

Covers the complete pickup and delivery lifecycles, cancellation with KDS
cleanup, and enforcement of invariants from WP-ST1 and WP-ST2.

Uses the Order model directly (integration tests, not UI).
"""

from __future__ import annotations

import pytest

from shopman.orderman.exceptions import InvalidTransition
from shopman.orderman.models import Order
from shopman.models import Channel


@pytest.fixture
def channel(db):
    return Channel.objects.create(ref="e2e-test", name="E2E Test")


@pytest.fixture
def delivery_order(channel):
    return Order.objects.create(
        ref="E2E-DLV-001",
        channel_ref=channel.ref,
        status=Order.Status.NEW,
        total_q=5000,
        data={"fulfillment_type": "delivery"},
    )


@pytest.fixture
def pickup_order(channel):
    return Order.objects.create(
        ref="E2E-PKP-001",
        channel_ref=channel.ref,
        status=Order.Status.NEW,
        total_q=3000,
        data={"fulfillment_type": "pickup"},
    )


# ── Pickup complete lifecycle ────────────────────────────────────────────────


@pytest.mark.django_db
def test_pickup_complete_lifecycle(pickup_order):
    """Pickup: new → confirmed → preparing → ready → completed."""
    o = pickup_order
    o.transition_status(Order.Status.CONFIRMED, actor="test")
    assert o.status == Order.Status.CONFIRMED

    o.transition_status(Order.Status.PREPARING, actor="test")
    assert o.status == Order.Status.PREPARING
    o.refresh_from_db()
    assert o.preparing_at is not None

    o.transition_status(Order.Status.READY, actor="test")
    assert o.status == Order.Status.READY

    o.transition_status(Order.Status.COMPLETED, actor="test")
    assert o.status == Order.Status.COMPLETED
    o.refresh_from_db()
    assert o.completed_at is not None


@pytest.mark.django_db
def test_pickup_cannot_reach_dispatched(pickup_order):
    """Pickup: dispatched is unreachable — Kernel enforces it."""
    o = pickup_order
    o.transition_status(Order.Status.CONFIRMED, actor="test")
    o.transition_status(Order.Status.PREPARING, actor="test")
    o.transition_status(Order.Status.READY, actor="test")

    with pytest.raises(InvalidTransition) as exc_info:
        o.transition_status(Order.Status.DISPATCHED, actor="test")

    assert exc_info.value.code == "dispatched_requires_delivery"


# ── Delivery complete lifecycle ──────────────────────────────────────────────


@pytest.mark.django_db
def test_delivery_complete_lifecycle(delivery_order):
    """Delivery: new → confirmed → preparing → ready → dispatched → delivered → completed."""
    o = delivery_order
    o.transition_status(Order.Status.CONFIRMED, actor="test")
    o.transition_status(Order.Status.PREPARING, actor="test")
    o.transition_status(Order.Status.READY, actor="test")
    o.transition_status(Order.Status.DISPATCHED, actor="test")
    assert o.status == Order.Status.DISPATCHED
    o.refresh_from_db()
    assert o.dispatched_at is not None

    o.transition_status(Order.Status.DELIVERED, actor="test")
    assert o.status == Order.Status.DELIVERED
    o.refresh_from_db()
    assert o.delivered_at is not None

    o.transition_status(Order.Status.COMPLETED, actor="test")
    assert o.status == Order.Status.COMPLETED


# ── Cancellation with KDS cleanup ───────────────────────────────────────────


@pytest.mark.django_db
def test_cancellation_while_preparing_cleans_kds_tickets(channel):
    """Order cancelled while preparing: KDS open tickets become cancelled."""
    from shopman.models import KDSInstance, KDSTicket

    order = Order.objects.create(
        ref="E2E-CANCEL-001",
        channel_ref=channel.ref,
        status=Order.Status.CONFIRMED,
        total_q=2000,
    )
    order.transition_status(Order.Status.PREPARING, actor="test")

    inst = KDSInstance.objects.create(ref="e2e-kds-1", name="E2E KDS", type="prep")
    t1 = KDSTicket.objects.create(order=order, kds_instance=inst, items=[], status="open")
    t2 = KDSTicket.objects.create(order=order, kds_instance=inst, items=[], status="open")

    from shopman.services.kds import cancel_tickets
    count = cancel_tickets(order)

    assert count == 2
    t1.refresh_from_db()
    t2.refresh_from_db()
    assert t1.status == "cancelled"
    assert t2.status == "cancelled"


# ── returned is terminal ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_returned_is_terminal(delivery_order):
    """returned → completed raises InvalidTransition (returned is terminal)."""
    o = delivery_order
    o.transition_status(Order.Status.CONFIRMED, actor="test")
    o.transition_status(Order.Status.PREPARING, actor="test")
    o.transition_status(Order.Status.READY, actor="test")
    o.transition_status(Order.Status.DISPATCHED, actor="test")
    o.transition_status(Order.Status.DELIVERED, actor="test")
    o.transition_status(Order.Status.RETURNED, actor="test")

    assert o.status == Order.Status.RETURNED

    with pytest.raises(InvalidTransition):
        o.transition_status(Order.Status.COMPLETED, actor="test")


@pytest.mark.django_db
def test_returned_is_in_terminal_statuses():
    """returned is listed in TERMINAL_STATUSES."""
    assert Order.Status.RETURNED in Order.TERMINAL_STATUSES
    assert Order.Status.COMPLETED in Order.TERMINAL_STATUSES
    assert Order.Status.CANCELLED in Order.TERMINAL_STATUSES


# ── dispatched requires delivery ─────────────────────────────────────────────


@pytest.mark.django_db
def test_dispatched_requires_delivery_invariant(channel):
    """Kernel enforces dispatched-requires-delivery for any non-delivery fulfillment."""
    for ft in ("pickup", "balcao", "totem"):
        order = Order.objects.create(
            ref=f"E2E-GUARD-{ft}",
            channel_ref=channel.ref,
            status=Order.Status.NEW,
            total_q=1000,
            data={"fulfillment_type": ft},
        )
        order.transition_status(Order.Status.CONFIRMED, actor="test")
        order.transition_status(Order.Status.PREPARING, actor="test")
        order.transition_status(Order.Status.READY, actor="test")

        with pytest.raises(InvalidTransition) as exc_info:
            order.transition_status(Order.Status.DISPATCHED, actor="test")

        assert exc_info.value.code == "dispatched_requires_delivery", (
            f"Expected dispatched_requires_delivery for fulfillment_type={ft}"
        )
