"""Persona 4 — Future preorder (encomenda).

Schedules an order for a future date. Preorder is a first-class citizen on the
``web`` channel (WP-A/B/C): a future-dated commit registers demand even when no
batch is planned, rather than refusing. Availability is a function of *when* —
perishable items (``shelf_life_days == 0``) are only promisable from a batch
planned for that exact day, non-perishable stock covers any future date.

The authoritative rejections at commit are calendar-based: a closed day, a date
in the past, or a date beyond the preorder window.
"""

from __future__ import annotations

from datetime import date

import pytest
from shopman.orderman.models import Order
from shopman.stockman.models import Hold

from . import _journey as J

pytestmark = pytest.mark.django_db

DURAVEL = "PAO-DURAVEL"   # non-perishable (shelf_life_days=None)
FRESCA = "BAGUETE-FRESCA"  # perishable (shelf_life_days=0)

WEEK = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _seed_shop(*, max_preorder_days=30, closed_dates=None):
    hours = {d: {"open": "08:00", "close": "18:00"} for d in WEEK}
    defaults = {"max_preorder_days": max_preorder_days}
    if closed_dates:
        defaults["closed_dates"] = [{"date": d, "label": "Feriado"} for d in closed_dates]
    J.seed_shop(opening_hours=hours, defaults=defaults)
    J.seed_web_channel()


def _holds_for_order(order) -> list[Hold]:
    return [
        Hold.objects.get(pk=int(e["hold_id"].split(":")[1]))
        for e in (order.data.get("hold_ids") or [])
        if e.get("hold_id")
    ]


# ── happy paths ──────────────────────────────────────────────────────────────


def test_preorder_nonperishable_three_days_out(client):
    _seed_shop()
    collection = J.seed_collection()
    J.seed_product(DURAVEL, "Pão durável", 1000, collection=collection, stock_qty=10, shelf_life_days=None)
    J.otp_login(client)

    J.set_cart_qty(client, DURAVEL, 2)
    target = J.days_ahead_iso(3)
    status, resp = J.checkout(
        client, fulfillment_type="pickup", delivery_date=target, delivery_time_slot=J.first_pickup_slot()
    )
    assert status == 201, resp

    order = Order.objects.get(ref=resp["order_ref"])
    assert order.data.get("is_preorder") is True
    holds = _holds_for_order(order)
    assert holds, "a preorder must register demand for the target date"
    assert all(h.target_date.isoformat() == target for h in holds)


def test_perishable_preorder_with_batch_planned_on_date_reserves_it(client):
    _seed_shop()
    collection = J.seed_collection()
    target = J.days_ahead_iso(3)
    # Perishable, made-to-order (demand_ok so it is always addable to the bag),
    # with a batch planned for exactly the target day.
    product = J.seed_product(
        FRESCA, "Baguete fresca", 1200, collection=collection,
        shelf_life_days=0, availability_policy="demand_ok",
    )
    J.plan_stock(product, 5, date.fromisoformat(target))
    J.otp_login(client)

    J.set_cart_qty(client, FRESCA, 2)
    status, resp = J.checkout(
        client, fulfillment_type="pickup", delivery_date=target, delivery_time_slot=J.first_pickup_slot()
    )
    assert status == 201, resp

    order = Order.objects.get(ref=resp["order_ref"])
    holds = _holds_for_order(order)
    assert holds
    assert all(h.target_date.isoformat() == target for h in holds)
    # A planned batch exists for the date → the hold binds to a planned Quant.
    assert any(h.quant is not None for h in holds), "expected a planned reservation"


def test_perishable_preorder_without_plan_for_the_date_registers_demand(client):
    _seed_shop()
    collection = J.seed_collection()
    product = J.seed_product(
        FRESCA, "Baguete fresca", 1200, collection=collection,
        shelf_life_days=0, availability_policy="demand_ok",
    )
    # A batch planned for *today* makes the SKU tracked, but a perishable batch is
    # only valid on its production day — so a +3 delivery has no valid supply and
    # the commit registers pure demand for that date.
    J.plan_stock(product, 5, date.today())
    J.otp_login(client)

    J.set_cart_qty(client, FRESCA, 2)
    target = J.days_ahead_iso(3)
    status, resp = J.checkout(
        client, fulfillment_type="pickup", delivery_date=target, delivery_time_slot=J.first_pickup_slot()
    )
    assert status == 201, resp  # first-class encomenda, not a refusal

    order = Order.objects.get(ref=resp["order_ref"])
    holds = _holds_for_order(order)
    assert holds
    # No plan for the date → the hold is pure demand (no Quant), indefinite.
    assert all(h.quant is None for h in holds)
    assert all(h.target_date.isoformat() == target for h in holds)


# ── calendar rejections ──────────────────────────────────────────────────────


def test_closed_day_is_rejected(client):
    closed = J.days_ahead_iso(5)
    _seed_shop(closed_dates=[closed])
    collection = J.seed_collection()
    J.seed_product(DURAVEL, "Pão durável", 1000, collection=collection, stock_qty=10)
    J.otp_login(client)

    J.set_cart_qty(client, DURAVEL, 1)
    status, body = J.checkout(
        client, fulfillment_type="pickup", delivery_date=closed, delivery_time_slot=J.first_pickup_slot()
    )
    assert status == 400, body
    assert body["field"] == "delivery_date"
    assert "fechados" in body["detail"].lower()


def test_past_date_is_rejected(client):
    _seed_shop()
    collection = J.seed_collection()
    J.seed_product(DURAVEL, "Pão durável", 1000, collection=collection, stock_qty=10)
    J.otp_login(client)

    J.set_cart_qty(client, DURAVEL, 1)
    status, body = J.checkout(
        client, fulfillment_type="pickup", delivery_date=J.days_ahead_iso(-1),
        delivery_time_slot=J.first_pickup_slot(),
    )
    assert status == 400, body
    assert "passada" in body["detail"].lower()


def test_beyond_preorder_window_is_rejected(client):
    _seed_shop(max_preorder_days=2)
    collection = J.seed_collection()
    J.seed_product(DURAVEL, "Pão durável", 1000, collection=collection, stock_qty=10)
    J.otp_login(client)

    J.set_cart_qty(client, DURAVEL, 1)
    status, body = J.checkout(
        client, fulfillment_type="pickup", delivery_date=J.days_ahead_iso(10),
        delivery_time_slot=J.first_pickup_slot(),
    )
    assert status == 400, body
    assert "máxima" in body["detail"].lower()
