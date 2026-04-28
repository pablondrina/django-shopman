from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from shopman.backstage.projections.order_queue import build_operator_order
from shopman.backstage.projections.production import build_work_order_card
from shopman.backstage.services.production import ProductionOrderShortError, apply_planned
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.orderman.models import Order, OrderItem
from shopman.shop.handlers.production_order_sync import (
    link_order_to_work_orders,
    link_work_order_to_orders,
    order_requirement_for_work_order,
)
from shopman.shop.models import Shop


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        ref="sync-croissant",
        name="Croissant",
        output_sku="CROISSANT",
        batch_size=Decimal("10"),
    )


def _order(ref: str, sku: str = "CROISSANT", qty: int = 2, status: str = "confirmed") -> Order:
    order = Order.objects.create(ref=ref, channel_ref="web", status=status, total_q=1000, data={"target_date": date.today().isoformat()})
    OrderItem.objects.create(order=order, line_id=f"{ref}-1", sku=sku, name=sku, qty=qty, unit_price_q=500, line_total_q=1000)
    return order


@pytest.mark.django_db
def test_confirmed_order_links_existing_planned_work_order(recipe):
    wo = craft.plan(recipe, 10, date=date.today(), position_ref="")
    order = _order("SYNC-ORD-1")

    link_order_to_work_orders(order=order, event_type="status_changed")

    order.refresh_from_db()
    wo.refresh_from_db()
    assert order.data["awaiting_wo_refs"] == [wo.ref]
    assert wo.meta["serves_order_refs"] == [order.ref]


@pytest.mark.django_db
def test_order_without_produced_recipe_does_not_link(recipe):
    order = _order("SYNC-ORD-2", sku="AGUA")

    link_order_to_work_orders(order=order, event_type="status_changed")

    order.refresh_from_db()
    assert "awaiting_wo_refs" not in order.data


@pytest.mark.django_db
def test_finished_work_order_progress_is_projected_for_order(recipe):
    wo = craft.plan(recipe, 10, date=date.today())
    craft.start(wo, quantity=10, expected_rev=0)
    craft.finish(wo, finished=8, actor="test")
    order = _order("SYNC-ORD-3")
    order.data = {"awaiting_wo_refs": [wo.ref]}
    order.save(update_fields=["data", "updated_at"])

    detail = build_operator_order(order)

    assert detail.awaiting_work_orders[0].ref == wo.ref
    assert detail.awaiting_work_orders[0].progress_pct == 80


@pytest.mark.django_db
def test_work_order_card_lists_served_orders(recipe):
    wo = craft.plan(recipe, 10, date=date.today())
    order = _order("SYNC-ORD-4", qty=3)
    wo.meta = {"serves_order_refs": [order.ref]}
    wo.save(update_fields=["meta", "updated_at"])

    card = build_work_order_card(wo.ref)

    assert card.serves_orders[0].ref == order.ref
    assert card.serves_orders[0].qty_required == "3"


@pytest.mark.django_db
def test_work_order_void_removes_bidirectional_refs(recipe):
    wo = craft.plan(recipe, 10, date=date.today())
    order = _order("SYNC-ORD-5")
    order.data = {"awaiting_wo_refs": [wo.ref]}
    order.save(update_fields=["data", "updated_at"])
    wo.meta = {"serves_order_refs": [order.ref]}
    wo.save(update_fields=["meta", "updated_at"])

    link_work_order_to_orders(action="voided", work_order=wo)

    order.refresh_from_db()
    wo.refresh_from_db()
    assert "awaiting_wo_refs" not in order.data
    assert "serves_order_refs" not in wo.meta


@pytest.mark.django_db
def test_earliest_target_strategy_prefers_older_work_order(recipe):
    Shop.objects.create(name="Loja", defaults={"production_order_match": "earliest_target"})
    newer = craft.plan(recipe, 10, date=date.today())
    older = craft.plan(recipe, 10, date=date.today() - timedelta(days=1))
    order = _order("SYNC-ORD-6")

    link_order_to_work_orders(order=order, event_type="status_changed")

    order.refresh_from_db()
    assert order.data["awaiting_wo_refs"] == [older.ref]
    assert newer.ref not in order.data["awaiting_wo_refs"]


@pytest.mark.django_db
def test_order_requirement_sums_linked_order_items(recipe):
    wo = craft.plan(recipe, 10, date=date.today())
    first = _order("SYNC-ORD-7", qty=2)
    second = _order("SYNC-ORD-8", qty=4)
    wo.meta = {"serves_order_refs": [first.ref, second.ref]}
    wo.save(update_fields=["meta", "updated_at"])

    assert order_requirement_for_work_order(wo) == Decimal("6")


@pytest.mark.django_db
def test_reducing_planned_below_linked_orders_requires_force(recipe):
    wo = craft.plan(recipe, 10, date=date.today(), position_ref="", operator_ref="")
    order = _order("SYNC-ORD-9", qty=8)
    wo.meta = {"serves_order_refs": [order.ref]}
    wo.save(update_fields=["meta", "updated_at"])

    with pytest.raises(ProductionOrderShortError):
        apply_planned(
            recipe_id=recipe.pk,
            quantity="5",
            target_date_value=date.today().isoformat(),
            position_ref="",
            operator_ref="",
            actor="test",
        )

    apply_planned(
        recipe_id=recipe.pk,
        quantity="5",
        target_date_value=date.today().isoformat(),
        position_ref="",
        operator_ref="",
        actor="test",
        force=True,
    )
    wo.refresh_from_db()
    assert wo.quantity == Decimal("5")
