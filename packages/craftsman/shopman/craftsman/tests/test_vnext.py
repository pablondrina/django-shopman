"""
Tests for Craftsman vNext — 4 verbs + 3 queries + invariants.
"""

import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import ANY

from shopman.craftsman import craft, CraftError, StaleRevision
from shopman.craftsman.models import (
    Recipe,
    RecipeItem,
    WorkOrder,
    WorkOrderEvent,
    WorkOrderItem,
)


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def recipe(db):
    """Simple recipe: 10 croissants."""
    return Recipe.objects.create(
        code="croissant-v1",
        name="Croissant Tradicional",
        output_ref="croissant",
        batch_size=Decimal("10"),
        steps=["Mistura", "Modelagem", "Forno"],
    )


@pytest.fixture
def recipe_with_items(recipe):
    """Recipe with 3 ingredients."""
    RecipeItem.objects.create(recipe=recipe, input_ref="farinha", quantity=Decimal("5"), unit="kg", sort_order=0)
    RecipeItem.objects.create(recipe=recipe, input_ref="agua", quantity=Decimal("3"), unit="L", sort_order=1)
    RecipeItem.objects.create(recipe=recipe, input_ref="fermento", quantity=Decimal("0.100"), unit="kg", sort_order=2)
    return recipe


@pytest.fixture
def recipe_simple(db):
    """Minimal recipe without steps."""
    return Recipe.objects.create(
        code="pao-simples",
        name="Pao Simples",
        output_ref="pao",
        batch_size=Decimal("1"),
    )


@pytest.fixture
def sub_recipe(db):
    """Sub-recipe for multilevel BOM: massa-base produces massa."""
    r = Recipe.objects.create(
        code="massa-base",
        name="Massa Base",
        output_ref="massa",
        batch_size=Decimal("5"),
    )
    RecipeItem.objects.create(recipe=r, input_ref="farinha", quantity=Decimal("3"), unit="kg")
    RecipeItem.objects.create(recipe=r, input_ref="agua", quantity=Decimal("2"), unit="L")
    return r


@pytest.fixture
def tomorrow():
    return date(2026, 2, 25)


# ══════════════════════════════════════════════════════════════
# PLAN
# ══════════════════════════════════════════════════════════════


class TestPlan:
    def test_plan_single(self, recipe, tomorrow):
        wo = craft.plan(recipe, 100, date=tomorrow)

        assert wo.ref.startswith("WO-")
        assert wo.recipe == recipe
        assert wo.output_ref == "croissant"
        assert wo.quantity == Decimal("100")
        assert wo.finished is None
        assert wo.status == WorkOrder.Status.PLANNED
        assert wo.scheduled_date == tomorrow
        assert wo.rev == 0

    def test_plan_generates_unique_ref(self, recipe):
        wo1 = craft.plan(recipe, 10)
        wo2 = craft.plan(recipe, 20)

        assert wo1.ref != wo2.ref
        assert wo1.ref.startswith("WO-2026-")
        assert wo2.ref.startswith("WO-2026-")

    def test_plan_creates_event(self, recipe):
        wo = craft.plan(recipe, 50)

        events = wo.events.all()
        assert events.count() == 1

        ev = events[0]
        assert ev.seq == 0
        assert ev.kind == "planned"
        assert ev.payload["quantity"] == "50"
        assert ev.payload["recipe"] == "croissant-v1"

    def test_plan_batch(self, recipe, recipe_simple, tomorrow):
        orders = craft.plan([
            (recipe, 100),
            (recipe_simple, 45),
        ], date=tomorrow)

        assert len(orders) == 2
        assert orders[0].output_ref == "croissant"
        assert orders[0].quantity == Decimal("100")
        assert orders[1].output_ref == "pao"
        assert orders[1].quantity == Decimal("45")

    def test_plan_with_kwargs(self, recipe):
        wo = craft.plan(
            recipe, 100,
            source_ref="order:123",
            position_ref="station:forno-01",
            assigned_ref="user:joao",
            actor="system:scheduler",
        )

        assert wo.source_ref == "order:123"
        assert wo.position_ref == "station:forno-01"
        assert wo.assigned_ref == "user:joao"
        assert wo.events.first().actor == "system:scheduler"

    def test_plan_invalid_quantity(self, recipe):
        with pytest.raises(CraftError) as exc:
            craft.plan(recipe, 0)
        assert exc.value.code == "INVALID_QUANTITY"

        with pytest.raises(CraftError):
            craft.plan(recipe, -5)

    def test_plan_no_quantity(self, recipe):
        with pytest.raises(CraftError) as exc:
            craft.plan(recipe, None)
        assert exc.value.code == "INVALID_QUANTITY"

    def test_plan_emits_signal(self, recipe, tomorrow):
        received = []

        from shopman.craftsman.signals import production_changed

        def handler(sender, product_ref, date, **kwargs):
            received.append((product_ref, date))

        production_changed.connect(handler)
        try:
            craft.plan(recipe, 100, date=tomorrow)
            assert len(received) == 1
            assert received[0] == ("croissant", tomorrow)
        finally:
            production_changed.disconnect(handler)


# ══════════════════════════════════════════════════════════════
# ADJUST
# ══════════════════════════════════════════════════════════════


class TestAdjust:
    def test_adjust_changes_quantity(self, recipe):
        wo = craft.plan(recipe, 100)
        craft.adjust(wo, quantity=97, reason="farinha insuficiente")

        wo.refresh_from_db()
        assert wo.quantity == Decimal("97")

    def test_adjust_bumps_rev(self, recipe):
        wo = craft.plan(recipe, 100)
        assert wo.rev == 0

        craft.adjust(wo, quantity=97)
        assert wo.rev == 1

    def test_adjust_creates_event(self, recipe):
        wo = craft.plan(recipe, 100)
        craft.adjust(wo, quantity=97, reason="farinha insuficiente", actor="joao")

        events = list(wo.events.order_by("seq"))
        assert len(events) == 2
        assert events[1].kind == "adjusted"
        assert Decimal(events[1].payload["from"]) == Decimal("100")
        assert Decimal(events[1].payload["to"]) == Decimal("97")
        assert events[1].payload["reason"] == "farinha insuficiente"
        assert events[1].actor == "joao"

    def test_adjust_does_not_start_work_order(self, recipe):
        wo = craft.plan(recipe, 100)
        assert wo.started_at is None

        craft.adjust(wo, quantity=97)
        wo.refresh_from_db()
        assert wo.started_at is None
        assert wo.status == WorkOrder.Status.PLANNED

    def test_adjust_with_rev_check(self, recipe):
        wo = craft.plan(recipe, 100)
        craft.adjust(wo, quantity=97, expected_rev=0)
        assert wo.rev == 1

    def test_adjust_stale_rev(self, recipe):
        wo = craft.plan(recipe, 100)
        craft.adjust(wo, quantity=97)  # rev now 1

        with pytest.raises(StaleRevision):
            craft.adjust(wo, quantity=95, expected_rev=0)  # stale!

    def test_adjust_terminal_status(self, recipe):
        wo = craft.plan(recipe, 100)
        craft.finish(wo, finished=93, expected_rev=0)

        with pytest.raises(CraftError) as exc:
            craft.adjust(wo, quantity=50)
        assert exc.value.code == "INVALID_STATUS"

    def test_adjust_emits_signal(self, recipe):
        wo = craft.plan(recipe, 100)
        received = []

        from shopman.craftsman.signals import production_changed

        def handler(sender, product_ref, date, **kwargs):
            received.append(product_ref)

        production_changed.connect(handler)
        try:
            craft.adjust(wo, quantity=97)
            assert "croissant" in received
        finally:
            production_changed.disconnect(handler)

    def test_adjust_invalid_quantity(self, recipe):
        wo = craft.plan(recipe, 100)
        with pytest.raises(CraftError) as exc:
            craft.adjust(wo, quantity=-5)
        assert exc.value.code == "INVALID_QUANTITY"

    def test_adjust_zero_voids(self, recipe):
        """adjust(quantity=0) voids the WorkOrder instead of raising."""
        wo = craft.plan(recipe, 100)
        craft.adjust(wo, quantity=0, reason="Remanejo: zerado")
        wo.refresh_from_db()
        assert wo.status == WorkOrder.Status.VOID


class TestFloorExecution:
    def test_start_sets_started_at_and_event(self, recipe):
        wo = craft.plan(recipe, 100)

        craft.start(
            wo,
            quantity=Decimal("92"),
            expected_rev=0,
            actor="joao",
            assigned_ref="user:joao",
            position_ref="station:forno-01",
            note="massa na bancada",
        )

        wo.refresh_from_db()
        assert wo.status == WorkOrder.Status.STARTED
        assert wo.started_at is not None
        assert wo.assigned_ref == "user:joao"
        assert wo.position_ref == "station:forno-01"
        assert wo.started_qty == Decimal("92")
        assert wo.rev == 1

        ev = wo.events.order_by("seq").last()
        assert ev.kind == "started"
        assert ev.payload["quantity"] == "92"
        assert ev.payload["assigned_ref"] == "user:joao"
        assert ev.payload["position_ref"] == "station:forno-01"
        assert ev.payload["note"] == "massa na bancada"
        assert ev.actor == "joao"

    def test_finish_uses_started_qty_as_execution_base(self, recipe):
        wo = craft.plan(recipe, 100)
        craft.start(wo, quantity=Decimal("92"), expected_rev=0, actor="joao")
        craft.finish(wo, finished=Decimal("89"), expected_rev=1, actor="joao")

        wo.refresh_from_db()
        assert wo.status == WorkOrder.Status.FINISHED
        assert wo.finished == Decimal("89")
        assert wo.started_qty == Decimal("92")
        assert wo.loss == Decimal("3")
        ev = wo.events.order_by("seq").last()
        assert ev.kind == "finished"
        assert ev.payload["planned_qty"] == "100.000"
        assert ev.payload["started_qty"] == "92"
        assert ev.payload["finished_qty"] == "89"

    def test_work_order_projection_tracks_floor_progress(self, recipe):
        wo = craft.plan(recipe, 100)
        assert wo.planned_qty == Decimal("100")
        assert wo.started_qty is None
        assert wo.finished_qty is None

        craft.start(wo, quantity=Decimal("92"), expected_rev=0)
        craft.finish(wo, finished=Decimal("89"), expected_rev=1)

        wo.refresh_from_db()
        assert wo.planned_qty == Decimal("100")
        assert wo.started_qty == Decimal("92")
        assert wo.finished_qty == Decimal("89")


# ══════════════════════════════════════════════════════════════
# FINISH
# ══════════════════════════════════════════════════════════════


class TestFinish:
    def test_finish_simple(self, recipe_with_items):
        wo = craft.plan(recipe_with_items, 100)
        craft.finish(wo, finished=93, expected_rev=0)

        wo.refresh_from_db()
        assert wo.status == WorkOrder.Status.FINISHED
        assert wo.finished == Decimal("93")
        assert wo.finished_at is not None

    def test_finish_materializes_requirements(self, recipe_with_items):
        """French coefficient: 100/10 = 10x. Farinha: 5*10=50kg."""
        wo = craft.plan(recipe_with_items, 100)
        craft.finish(wo, finished=93, expected_rev=0)

        reqs = WorkOrderItem.objects.filter(work_order=wo, kind=WorkOrderItem.Kind.REQUIREMENT)
        assert reqs.count() == 3

        farinha = reqs.get(item_ref="farinha")
        assert farinha.quantity == Decimal("50.000")
        assert farinha.unit == "kg"

        agua = reqs.get(item_ref="agua")
        assert agua.quantity == Decimal("30.000")

        fermento = reqs.get(item_ref="fermento")
        assert fermento.quantity == Decimal("1.000")

    def test_finish_auto_consumption(self, recipe_with_items):
        """If consumed=None, consumption = requirements."""
        wo = craft.plan(recipe_with_items, 100)
        craft.finish(wo, finished=93, expected_rev=0)

        consumptions = WorkOrderItem.objects.filter(work_order=wo, kind=WorkOrderItem.Kind.CONSUMPTION)
        assert consumptions.count() == 3
        assert consumptions.get(item_ref="farinha").quantity == Decimal("50.000")

    def test_finish_explicit_consumed(self, recipe_with_items):
        wo = craft.plan(recipe_with_items, 100)
        craft.finish(wo, finished=93, consumed=[
            {"item_ref": "farinha", "quantity": 48.5, "unit": "kg"},
            {"item_ref": "agua", "quantity": 29, "unit": "L"},
            {"item_ref": "fermento", "quantity": "0.95", "unit": "kg"},
        ], expected_rev=0)

        consumptions = WorkOrderItem.objects.filter(work_order=wo, kind=WorkOrderItem.Kind.CONSUMPTION)
        assert consumptions.count() == 3
        assert consumptions.get(item_ref="farinha").quantity == Decimal("48.5")

    def test_finish_creates_output_item(self, recipe_with_items):
        wo = craft.plan(recipe_with_items, 100)
        craft.finish(wo, finished=93, expected_rev=0)

        outputs = WorkOrderItem.objects.filter(work_order=wo, kind=WorkOrderItem.Kind.OUTPUT)
        assert outputs.count() == 1
        assert outputs[0].item_ref == "croissant"
        assert outputs[0].quantity == Decimal("93")

    def test_finish_auto_waste(self, recipe_with_items):
        """Auto waste: started_qty/planned_qty(100) - finished(93) = 7."""
        wo = craft.plan(recipe_with_items, 100)
        craft.finish(wo, finished=93, expected_rev=0)

        wastes = WorkOrderItem.objects.filter(work_order=wo, kind=WorkOrderItem.Kind.WASTE)
        assert wastes.count() == 1
        assert wastes[0].quantity == Decimal("7")
        assert wastes[0].item_ref == "croissant"

    def test_finish_no_waste_when_exact(self, recipe_with_items):
        """No waste when finished == quantity."""
        wo = craft.plan(recipe_with_items, 100)
        craft.finish(wo, finished=100, expected_rev=0)

        wastes = WorkOrderItem.objects.filter(work_order=wo, kind=WorkOrderItem.Kind.WASTE)
        assert wastes.count() == 0

    def test_finish_explicit_waste(self, recipe_with_items):
        wo = craft.plan(recipe_with_items, 100)
        craft.finish(wo, finished=93, wasted=[
            {"item_ref": "croissant", "quantity": 3, "meta": {"reason": "queimado"}},
            {"item_ref": "massa", "quantity": 2, "unit": "kg", "meta": {"reason": "caiu"}},
        ], expected_rev=0)

        wastes = WorkOrderItem.objects.filter(work_order=wo, kind=WorkOrderItem.Kind.WASTE)
        assert wastes.count() == 2

    def test_finish_idempotency(self, recipe_with_items):
        wo = craft.plan(recipe_with_items, 100)
        result1 = craft.finish(wo, finished=93, expected_rev=0, idempotency_key="finish-001")

        # Second call with same key — returns without mutating
        result2 = craft.finish(wo, finished=50, idempotency_key="finish-001")
        assert result2.pk == result1.pk
        assert result2.finished == Decimal("93")  # original value preserved

    def test_finish_bumps_rev(self, recipe):
        wo = craft.plan(recipe, 100)
        craft.finish(wo, finished=93, expected_rev=0)
        wo.refresh_from_db()
        assert wo.rev == 1

    def test_finish_stale_rev(self, recipe):
        wo = craft.plan(recipe, 100)
        craft.adjust(wo, quantity=97)  # rev now 1

        with pytest.raises(StaleRevision):
            craft.finish(wo, finished=93, expected_rev=0)

    def test_finish_terminal_status(self, recipe):
        wo = craft.plan(recipe, 100)
        craft.finish(wo, finished=93, expected_rev=0)

        with pytest.raises(CraftError) as exc:
            craft.finish(wo, finished=50, expected_rev=1)
        assert exc.value.code == "TERMINAL_STATUS"

    def test_finish_creates_event(self, recipe):
        wo = craft.plan(recipe, 100)
        craft.finish(wo, finished=93, expected_rev=0, actor="operador")

        events = list(wo.events.order_by("seq"))
        assert len(events) == 3
        assert events[1].kind == "started"
        assert events[1].payload["implicit"] is True
        assert events[2].kind == "finished"
        assert events[2].payload["finished_qty"] == "93"
        assert events[2].actor == "operador"

    def test_finish_emits_signal(self, recipe):
        wo = craft.plan(recipe, 100)
        received = []

        from shopman.craftsman.signals import production_changed

        def handler(sender, product_ref, date, **kwargs):
            received.append(product_ref)

        production_changed.connect(handler)
        try:
            craft.finish(wo, finished=93, expected_rev=0)
            assert "croissant" in received
        finally:
            production_changed.disconnect(handler)

    def test_finish_with_lot_tracking(self, recipe_with_items):
        """Lot tracking via meta on consumed items."""
        wo = craft.plan(recipe_with_items, 100)
        craft.finish(wo, finished=93, consumed=[
            {"item_ref": "farinha", "quantity": 50, "unit": "kg",
             "meta": {"lot": "FAR-2026-02-23"}},
            {"item_ref": "agua", "quantity": 30, "unit": "L"},
            {"item_ref": "fermento", "quantity": 1, "unit": "kg",
             "meta": {"lot": "FER-2026-02-20", "expires": "2026-03-20"}},
        ], expected_rev=0)

        farinha = WorkOrderItem.objects.get(
            work_order=wo, kind=WorkOrderItem.Kind.CONSUMPTION, item_ref="farinha",
        )
        assert farinha.meta["lot"] == "FAR-2026-02-23"


# ══════════════════════════════════════════════════════════════
# VOID
# ══════════════════════════════════════════════════════════════


class TestVoid:
    def test_void_from_planned(self, recipe):
        wo = craft.plan(recipe, 100)
        craft.void(wo, reason="cliente cancelou", expected_rev=0)

        wo.refresh_from_db()
        assert wo.status == WorkOrder.Status.VOID

    def test_void_creates_event(self, recipe):
        wo = craft.plan(recipe, 100)
        craft.void(wo, reason="cancelado", expected_rev=0, actor="operador")

        events = list(wo.events.order_by("seq"))
        assert len(events) == 2
        assert events[1].kind == "voided"
        assert events[1].payload["reason"] == "cancelado"
        assert events[1].actor == "operador"

    def test_void_from_finished_fails(self, recipe):
        wo = craft.plan(recipe, 100)
        craft.finish(wo, finished=93, expected_rev=0)

        with pytest.raises(CraftError) as exc:
            craft.void(wo, reason="teste", expected_rev=1)
        assert exc.value.code == "VOID_FROM_DONE"

    def test_void_from_void_fails(self, recipe):
        wo = craft.plan(recipe, 100)
        craft.void(wo, reason="primeiro", expected_rev=0)

        with pytest.raises(CraftError) as exc:
            craft.void(wo, reason="segundo", expected_rev=1)
        assert exc.value.code == "TERMINAL_STATUS"

    def test_void_stale_rev(self, recipe):
        wo = craft.plan(recipe, 100)
        craft.adjust(wo, quantity=97)

        with pytest.raises(StaleRevision):
            craft.void(wo, reason="cancelado", expected_rev=0)

    def test_void_emits_signal(self, recipe):
        wo = craft.plan(recipe, 100)
        received = []

        from shopman.craftsman.signals import production_changed

        def handler(sender, product_ref, date, **kwargs):
            received.append(product_ref)

        production_changed.connect(handler)
        try:
            craft.void(wo, reason="cancelado", expected_rev=0)
            assert "croissant" in received
        finally:
            production_changed.disconnect(handler)


# ══════════════════════════════════════════════════════════════
# QUERIES
# ══════════════════════════════════════════════════════════════


class TestExpected:
    def test_expected_sums_active_orders(self, recipe, tomorrow):
        craft.plan(recipe, 100, date=tomorrow)
        craft.plan(recipe, 50, date=tomorrow)

        total = craft.expected("croissant", tomorrow)
        assert total == Decimal("150")

    def test_expected_excludes_finished(self, recipe, tomorrow):
        wo = craft.plan(recipe, 100, date=tomorrow)
        craft.finish(wo, finished=93, expected_rev=0)

        total = craft.expected("croissant", tomorrow)
        assert total == Decimal("0")

    def test_expected_excludes_void(self, recipe, tomorrow):
        wo = craft.plan(recipe, 100, date=tomorrow)
        craft.void(wo, reason="cancelado", expected_rev=0)

        total = craft.expected("croissant", tomorrow)
        assert total == Decimal("0")

    def test_expected_zero_when_none(self, tomorrow):
        total = craft.expected("nao-existe", tomorrow)
        assert total == Decimal("0")


class TestNeeds:
    def test_needs_basic(self, recipe_with_items, tomorrow):
        craft.plan(recipe_with_items, 100, date=tomorrow)

        needs = craft.needs(tomorrow)
        assert len(needs) == 3

        by_ref = {n.item_ref: n for n in needs}
        assert by_ref["farinha"].quantity == Decimal("50.000")
        assert by_ref["farinha"].unit == "kg"
        assert by_ref["farinha"].has_recipe is False
        assert by_ref["agua"].quantity == Decimal("30.000")

    def test_needs_aggregates_multiple_orders(self, recipe_with_items, tomorrow):
        craft.plan(recipe_with_items, 100, date=tomorrow)
        craft.plan(recipe_with_items, 50, date=tomorrow)

        needs = craft.needs(tomorrow)
        by_ref = {n.item_ref: n for n in needs}
        assert by_ref["farinha"].quantity == Decimal("75.000")  # 50 + 25

    def test_needs_has_recipe_flag(self, recipe_with_items, sub_recipe, tomorrow):
        """massa is a sub-recipe, so has_recipe=True."""
        RecipeItem.objects.create(
            recipe=recipe_with_items, input_ref="massa", quantity=Decimal("2"), unit="kg", sort_order=10,
        )
        craft.plan(recipe_with_items, 10, date=tomorrow)

        needs = craft.needs(tomorrow)
        by_ref = {n.item_ref: n for n in needs}
        assert by_ref["massa"].has_recipe is True
        assert by_ref["farinha"].has_recipe is False

    def test_needs_expand(self, recipe_with_items, sub_recipe, tomorrow):
        """Expand sub-recipe to raw materials."""
        RecipeItem.objects.create(
            recipe=recipe_with_items, input_ref="massa", quantity=Decimal("5"), unit="kg", sort_order=10,
        )
        craft.plan(recipe_with_items, 10, date=tomorrow)

        needs = craft.needs(tomorrow, expand=True)
        by_ref = {n.item_ref: n for n in needs}

        # massa(5kg for 10 croissants) → coefficient=5/5=1 → farinha:3kg, agua:2L
        # plus direct farinha from croissant recipe: 5*1=5kg
        assert "massa" not in by_ref  # expanded away
        assert by_ref["farinha"].quantity == Decimal("8.000")  # 5 + 3

    def test_needs_empty_when_no_orders(self, tomorrow):
        needs = craft.needs(tomorrow)
        assert needs == []


# ══════════════════════════════════════════════════════════════
# INVARIANTS
# ══════════════════════════════════════════════════════════════


class TestInvariants:
    def test_quantity_always_positive(self, recipe):
        with pytest.raises(CraftError):
            craft.plan(recipe, 0)
        with pytest.raises(CraftError):
            craft.plan(recipe, -10)

    def test_finished_is_terminal(self, recipe):
        wo = craft.plan(recipe, 100)
        craft.finish(wo, finished=93, expected_rev=0)

        with pytest.raises(CraftError):
            craft.adjust(wo, quantity=50)
        with pytest.raises(CraftError):
            craft.void(wo, reason="teste", expected_rev=1)

    def test_void_is_terminal(self, recipe):
        wo = craft.plan(recipe, 100)
        craft.void(wo, reason="cancelado", expected_rev=0)

        with pytest.raises(CraftError):
            craft.adjust(wo, quantity=50)
        with pytest.raises(CraftError):
            craft.void(wo, reason="de novo", expected_rev=1)

    def test_rev_increments_by_one(self, recipe):
        wo = craft.plan(recipe, 100)
        assert wo.rev == 0

        craft.adjust(wo, quantity=97)
        assert wo.rev == 1

        craft.finish(wo, finished=93, expected_rev=1)
        wo.refresh_from_db()
        assert wo.rev == 2

    def test_events_sequential(self, recipe):
        wo = craft.plan(recipe, 100)
        craft.adjust(wo, quantity=97)
        craft.finish(wo, finished=93, expected_rev=1)

        events = list(wo.events.order_by("seq"))
        assert [e.seq for e in events] == [0, 1, 2, 3]
        assert [e.kind for e in events] == ["planned", "adjusted", "started", "finished"]

    def test_loss_and_yield(self, recipe):
        wo = craft.plan(recipe, 100)
        craft.finish(wo, finished=93, expected_rev=0)

        wo.refresh_from_db()
        assert wo.loss == Decimal("7")
        assert wo.yield_rate == Decimal("93") / Decimal("100")

    def test_loss_none_before_finish(self, recipe):
        wo = craft.plan(recipe, 100)
        assert wo.loss is None
        assert wo.yield_rate is None


# ══════════════════════════════════════════════════════════════
# MODEL BASICS
# ══════════════════════════════════════════════════════════════


class TestModels:
    def test_recipe_validation(self, db):
        with pytest.raises(Exception):
            Recipe.objects.create(
                code="bad", name="Bad", output_ref="x", batch_size=Decimal("0"),
            )

    def test_recipe_str(self, recipe):
        assert "Croissant" in str(recipe)

    def test_recipe_item_unique(self, recipe):
        RecipeItem.objects.create(recipe=recipe, input_ref="farinha", quantity=Decimal("5"), unit="kg")
        with pytest.raises(Exception):
            RecipeItem.objects.create(recipe=recipe, input_ref="farinha", quantity=Decimal("3"), unit="kg")

    def test_work_order_auto_ref(self, recipe):
        wo = WorkOrder.objects.create(recipe=recipe, output_ref="croissant", quantity=Decimal("10"))
        assert wo.ref.startswith("WO-2026-")

    def test_work_order_status_choices(self):
        assert WorkOrder.Status.PLANNED == "planned"
        assert WorkOrder.Status.STARTED == "started"
        assert WorkOrder.Status.FINISHED == "finished"
        assert WorkOrder.Status.VOID == "void"


# ── Protocol Imports ──────────────────────────────────────────


class TestProtocols:
    """Test that all protocols are importable and well-defined."""

    def test_inventory_protocol_importable(self):
        from shopman.craftsman.protocols import InventoryProtocol, StockBackend
        assert InventoryProtocol is StockBackend

    def test_catalog_protocol_importable(self):
        from shopman.craftsman.protocols import CatalogProtocol, ProductInfoBackend
        assert CatalogProtocol is not None
        assert ProductInfoBackend is not None

    def test_demand_protocol_importable(self):
        from shopman.craftsman.protocols import DemandProtocol, DemandBackend, DailyDemand
        assert DemandProtocol is DemandBackend
        assert DailyDemand is not None

    def test_inventory_dataclasses(self):
        from shopman.craftsman.protocols.inventory import (
            MaterialNeed, MaterialUsed, MaterialProduced,
            MaterialStatus, AvailabilityResult, MaterialHold,
            ReserveResult, ConsumeResult, ReleaseResult, ReceiveResult,
        )
        mn = MaterialNeed(sku="farinha", quantity=Decimal("10"))
        assert mn.sku == "farinha"
        assert mn.quantity == Decimal("10")

        mp = MaterialProduced(sku="croissant", quantity=Decimal("50"))
        assert mp.sku == "croissant"

    def test_catalog_dataclasses(self):
        from shopman.craftsman.protocols.catalog import ItemInfo
        info = ItemInfo(ref="farinha", name="Farinha T55", unit="kg")
        assert info.ref == "farinha"

    def test_demand_dataclasses(self):
        from shopman.craftsman.protocols.demand import DailyDemand
        dd = DailyDemand(date=date(2026, 2, 25), sold=Decimal("50"), wasted=Decimal("3"))
        assert dd.sold == Decimal("50")
        assert dd.soldout_at is None

    def test_backward_compat_stock_module(self):
        """protocols/stock.py still works as re-export."""
        from shopman.craftsman.protocols.stock import StockBackend, MaterialNeed
        assert StockBackend is not None
        assert MaterialNeed is not None

    def test_backward_compat_product_module(self):
        """protocols/product.py still works as re-export."""
        from shopman.craftsman.protocols.product import ProductInfoBackend, ProductInfo
        assert ProductInfoBackend is not None
        assert ProductInfo is not None


# ── Inventory Protocol Wiring ─────────────────────────────────


class TestInventoryWiring:
    """Test the inventory protocol integration in finish/void."""

    def test_finish_standalone_mode(self, recipe_with_items):
        """Without INVENTORY_BACKEND, finish succeeds (standalone)."""
        wo = craft.plan(recipe_with_items, 10)
        craft.finish(wo, finished=9)
        assert wo.status == "finished"

    def test_void_standalone_mode(self, recipe_with_items):
        """Without INVENTORY_BACKEND, void succeeds (standalone)."""
        wo = craft.plan(recipe_with_items, 10)
        craft.void(wo, reason="test")
        assert wo.status == "void"

    def test_finish_with_mock_backend(self, recipe_with_items, settings):
        """With configured backend, finish calls consume + receive."""
        from unittest.mock import MagicMock, patch

        mock_backend = MagicMock()
        mock_backend_class = MagicMock(return_value=mock_backend)

        settings.CRAFTSMAN = {
            "INVENTORY_BACKEND": "test.MockBackend",
        }

        wo = craft.plan(recipe_with_items, 10)

        with patch(
            "django.utils.module_loading.import_string",
            return_value=mock_backend_class,
        ):
            craft.finish(wo, finished=9)

        assert wo.status == "finished"
        assert mock_backend.consume.called
        assert mock_backend.receive.called

    def test_void_with_mock_backend(self, recipe_with_items, settings):
        """With configured backend, void calls release."""
        from unittest.mock import MagicMock, patch

        mock_backend = MagicMock()
        mock_backend_class = MagicMock(return_value=mock_backend)

        settings.CRAFTSMAN = {
            "INVENTORY_BACKEND": "test.MockBackend",
        }

        wo = craft.plan(recipe_with_items, 10)

        with patch(
            "django.utils.module_loading.import_string",
            return_value=mock_backend_class,
        ):
            craft.void(wo, reason="test")

        assert wo.status == "void"
        assert mock_backend.release.called

    def test_backend_failure_is_non_fatal(self, recipe_with_items, settings):
        """If backend raises, finish still succeeds (graceful degradation)."""
        from unittest.mock import MagicMock, patch

        mock_backend = MagicMock()
        mock_backend.consume.side_effect = RuntimeError("Stockman down")
        mock_backend_class = MagicMock(return_value=mock_backend)

        settings.CRAFTSMAN = {
            "INVENTORY_BACKEND": "test.MockBackend",
        }

        wo = craft.plan(recipe_with_items, 10)

        with patch(
            "django.utils.module_loading.import_string",
            return_value=mock_backend_class,
        ):
            # Should NOT raise — graceful degradation
            craft.finish(wo, finished=9)

        assert wo.status == "finished"
        assert wo.finished == Decimal("9")


# ══════════════════════════════════════════════════════════════
# SUGGEST
# ══════════════════════════════════════════════════════════════


class TestSuggest:
    """Tests for craft.suggest() — demand-based production suggestions."""

    def test_no_backend_returns_empty(self, recipe, tomorrow):
        """Without DEMAND_BACKEND configured, returns []."""
        result = craft.suggest(tomorrow)
        assert result == []

    def test_basic_suggestion(self, recipe, tomorrow, settings):
        """Basic suggest with uniform history data."""
        from datetime import time
        from unittest.mock import MagicMock, patch

        from shopman.craftsman.protocols.demand import DailyDemand

        mock_backend = MagicMock()
        mock_backend.history.return_value = [
            DailyDemand(date=date(2026, 2, 18), sold=Decimal("80"), wasted=Decimal("5")),
            DailyDemand(date=date(2026, 2, 11), sold=Decimal("100"), wasted=Decimal("3")),
            DailyDemand(date=date(2026, 2, 4), sold=Decimal("120"), wasted=Decimal("2")),
        ]
        mock_backend.committed.return_value = Decimal("0")
        mock_backend_class = MagicMock(return_value=mock_backend)

        settings.CRAFTSMAN = {"DEMAND_BACKEND": "test.MockDemandBackend"}

        with patch(
            "django.utils.module_loading.import_string",
            return_value=mock_backend_class,
        ):
            suggestions = craft.suggest(tomorrow)

        assert len(suggestions) == 1
        s = suggestions[0]
        assert s.recipe == recipe
        # avg = (80+100+120)/3 = 100, safety = 20% => 100 * 1.2 = 120
        assert s.quantity == Decimal("120")
        assert s.basis["avg_demand"] == Decimal("100")
        assert s.basis["committed"] == Decimal("0")
        assert s.basis["safety_pct"] == Decimal("0.20")
        assert s.basis["sample_size"] == 3

    def test_with_committed_demand(self, recipe, tomorrow, settings):
        """Committed demand is added before safety margin."""
        from unittest.mock import MagicMock, patch

        from shopman.craftsman.protocols.demand import DailyDemand

        mock_backend = MagicMock()
        mock_backend.history.return_value = [
            DailyDemand(date=date(2026, 2, 18), sold=Decimal("100"), wasted=Decimal("0")),
        ]
        mock_backend.committed.return_value = Decimal("30")
        mock_backend_class = MagicMock(return_value=mock_backend)

        settings.CRAFTSMAN = {"DEMAND_BACKEND": "test.MockDemandBackend"}

        with patch(
            "django.utils.module_loading.import_string",
            return_value=mock_backend_class,
        ):
            suggestions = craft.suggest(tomorrow)

        assert len(suggestions) == 1
        # avg=100, committed=30, safety=20% => (100+30)*1.2 = 156
        assert suggestions[0].quantity == Decimal("156")
        assert suggestions[0].basis["committed"] == Decimal("30")

    def test_soldout_extrapolation(self, recipe, tomorrow, settings):
        """When soldout_at is set, demand is extrapolated."""
        from datetime import time
        from unittest.mock import MagicMock, patch

        from shopman.craftsman.protocols.demand import DailyDemand

        mock_backend = MagicMock()
        # Sold 50 by 12:00 (6 hours from 06:00 open = 360 min)
        # Rate: 50/360; Full day: 50/360 * 720 = 100; cap = 100 (= 2*50)
        mock_backend.history.return_value = [
            DailyDemand(
                date=date(2026, 2, 18),
                sold=Decimal("50"),
                wasted=Decimal("0"),
                soldout_at=time(12, 0),
            ),
        ]
        mock_backend.committed.return_value = Decimal("0")
        mock_backend_class = MagicMock(return_value=mock_backend)

        settings.CRAFTSMAN = {"DEMAND_BACKEND": "test.MockDemandBackend"}

        with patch(
            "django.utils.module_loading.import_string",
            return_value=mock_backend_class,
        ):
            suggestions = craft.suggest(tomorrow)

        assert len(suggestions) == 1
        # Extrapolated: 100, safety 20% => 120
        assert suggestions[0].quantity == Decimal("120")

    def test_soldout_capped_at_2x(self, recipe, tomorrow, settings):
        """Extrapolation is capped at 2x actual sold."""
        from datetime import time
        from unittest.mock import MagicMock, patch

        from shopman.craftsman.protocols.demand import DailyDemand

        mock_backend = MagicMock()
        # Sold 50 by 07:00 (1 hour from 06:00 = 60 min)
        # Rate: 50/60; Full day: 50/60 * 720 = 600; cap = 2*50 = 100
        mock_backend.history.return_value = [
            DailyDemand(
                date=date(2026, 2, 18),
                sold=Decimal("50"),
                wasted=Decimal("0"),
                soldout_at=time(7, 0),
            ),
        ]
        mock_backend.committed.return_value = Decimal("0")
        mock_backend_class = MagicMock(return_value=mock_backend)

        settings.CRAFTSMAN = {"DEMAND_BACKEND": "test.MockDemandBackend"}

        with patch(
            "django.utils.module_loading.import_string",
            return_value=mock_backend_class,
        ):
            suggestions = craft.suggest(tomorrow)

        assert len(suggestions) == 1
        # Capped at 2*50=100, safety 20% => 120
        assert suggestions[0].quantity == Decimal("120")

    def test_empty_history_skips_recipe(self, recipe, tomorrow, settings):
        """Recipe with no history data is not included in suggestions."""
        from unittest.mock import MagicMock, patch

        mock_backend = MagicMock()
        mock_backend.history.return_value = []
        mock_backend_class = MagicMock(return_value=mock_backend)

        settings.CRAFTSMAN = {"DEMAND_BACKEND": "test.MockDemandBackend"}

        with patch(
            "django.utils.module_loading.import_string",
            return_value=mock_backend_class,
        ):
            suggestions = craft.suggest(tomorrow)

        assert suggestions == []

    def test_passes_settings_to_backend(self, recipe, tomorrow, settings):
        """HISTORICAL_DAYS and SAME_WEEKDAY_ONLY are passed to backend."""
        from unittest.mock import MagicMock, patch

        mock_backend = MagicMock()
        mock_backend.history.return_value = []
        mock_backend_class = MagicMock(return_value=mock_backend)

        settings.CRAFTSMAN = {
            "DEMAND_BACKEND": "test.MockDemandBackend",
            "HISTORICAL_DAYS": 14,
            "SAME_WEEKDAY_ONLY": False,
        }

        with patch(
            "django.utils.module_loading.import_string",
            return_value=mock_backend_class,
        ):
            craft.suggest(tomorrow)

        mock_backend.history.assert_called_once_with(
            recipe.output_ref,
            days=14,
            same_weekday=False,
        )

    def test_inactive_recipe_excluded(self, recipe, tomorrow, settings):
        """Inactive recipes should not generate suggestions."""
        from unittest.mock import MagicMock, patch

        recipe.is_active = False
        recipe.save()

        mock_backend = MagicMock()
        mock_backend_class = MagicMock(return_value=mock_backend)

        settings.CRAFTSMAN = {"DEMAND_BACKEND": "test.MockDemandBackend"}

        with patch(
            "django.utils.module_loading.import_string",
            return_value=mock_backend_class,
        ):
            suggestions = craft.suggest(tomorrow)

        assert suggestions == []
        mock_backend.history.assert_not_called()

    def test_suggest_with_season_filter(self, recipe, settings):
        """Season filter keeps only history records whose month is in season_months."""
        from unittest.mock import MagicMock, patch

        from shopman.craftsman.protocols.demand import DailyDemand

        mock_backend = MagicMock()
        # Mix of hot (Jan/Feb) and mild (Apr/May) months
        mock_backend.history.return_value = [
            DailyDemand(date=date(2025, 1, 8), sold=Decimal("100"), wasted=Decimal("0")),
            DailyDemand(date=date(2025, 2, 5), sold=Decimal("120"), wasted=Decimal("0")),
            DailyDemand(date=date(2025, 4, 2), sold=Decimal("50"), wasted=Decimal("0")),
            DailyDemand(date=date(2025, 5, 7), sold=Decimal("60"), wasted=Decimal("0")),
            DailyDemand(date=date(2025, 1, 15), sold=Decimal("110"), wasted=Decimal("0")),
            DailyDemand(date=date(2025, 1, 22), sold=Decimal("90"), wasted=Decimal("0")),
            DailyDemand(date=date(2025, 2, 12), sold=Decimal("130"), wasted=Decimal("0")),
            DailyDemand(date=date(2025, 2, 19), sold=Decimal("95"), wasted=Decimal("0")),
        ]
        mock_backend.committed.return_value = Decimal("0")
        mock_backend_class = MagicMock(return_value=mock_backend)

        settings.CRAFTSMAN = {"DEMAND_BACKEND": "test.MockDemandBackend"}

        target = date(2026, 1, 14)  # January = hot month
        hot_months = [10, 11, 12, 1, 2, 3]

        with patch("django.utils.module_loading.import_string", return_value=mock_backend_class):
            suggestions = craft.suggest(target, season_months=hot_months)

        assert len(suggestions) == 1
        s = suggestions[0]
        # Only 6 hot-month records used (Jan x4 + Feb x2 = sorted from history above)
        assert s.basis["sample_size"] == 6
        assert s.basis["season"] == "hot"
        assert s.basis["confidence"] == "medium"  # 6 records: >= 3 but < 8
        # avg of [100, 120, 110, 90, 130, 95] = 645/6 = 107.5; safety 20% => 107.5*1.2=129
        assert s.quantity == Decimal("129")

    def test_suggest_confidence_levels(self, recipe, settings):
        """Confidence is derived from sample_size: >=8 high, >=3 medium, >=1 low, 0 skip."""
        from unittest.mock import MagicMock, patch

        from shopman.craftsman.protocols.demand import DailyDemand

        def _make_history(n):
            return [
                DailyDemand(date=date(2025, 1, i + 1), sold=Decimal("100"), wasted=Decimal("0"))
                for i in range(n)
            ]

        def _run(n):
            mock_backend = MagicMock()
            mock_backend.history.return_value = _make_history(n)
            mock_backend.committed.return_value = Decimal("0")
            mock_backend_class = MagicMock(return_value=mock_backend)
            with patch("django.utils.module_loading.import_string", return_value=mock_backend_class):
                return craft.suggest(date(2026, 1, 14))

        settings.CRAFTSMAN = {"DEMAND_BACKEND": "test.MockDemandBackend"}

        # 10 records → high
        sugs = _run(10)
        assert sugs[0].basis["confidence"] == "high"

        # 5 records → medium
        sugs = _run(5)
        assert sugs[0].basis["confidence"] == "medium"

        # 1 record → low
        sugs = _run(1)
        assert sugs[0].basis["confidence"] == "low"

        # 0 records → no suggestion
        sugs = _run(0)
        assert sugs == []

    def test_suggest_waste_adjustment(self, recipe, settings):
        """High waste_rate (>15%) reduces avg_demand proportionally."""
        from unittest.mock import MagicMock, patch

        from shopman.craftsman.protocols.demand import DailyDemand

        mock_backend = MagicMock()
        # 5 records with 20% waste rate: sold=100, wasted=20 each
        mock_backend.history.return_value = [
            DailyDemand(date=date(2025, 1, i + 1), sold=Decimal("100"), wasted=Decimal("20"))
            for i in range(5)
        ]
        mock_backend.committed.return_value = Decimal("0")
        mock_backend_class = MagicMock(return_value=mock_backend)

        settings.CRAFTSMAN = {"DEMAND_BACKEND": "test.MockDemandBackend"}

        with patch("django.utils.module_loading.import_string", return_value=mock_backend_class):
            suggestions = craft.suggest(date(2026, 1, 14))

        assert len(suggestions) == 1
        s = suggestions[0]
        # waste_rate=20/100=0.20; avg_demand after adjustment=100*(1-0.20)=80
        # quantity=80*1.2=96
        assert s.basis["waste_rate"] == Decimal("0.20")
        assert s.quantity == Decimal("96")

    def test_suggest_waste_below_threshold_no_adjustment(self, recipe, settings):
        """Waste rate <= 15% does not reduce suggestion."""
        from unittest.mock import MagicMock, patch

        from shopman.craftsman.protocols.demand import DailyDemand

        mock_backend = MagicMock()
        mock_backend.history.return_value = [
            DailyDemand(date=date(2025, 1, i + 1), sold=Decimal("100"), wasted=Decimal("10"))
            for i in range(5)
        ]
        mock_backend.committed.return_value = Decimal("0")
        mock_backend_class = MagicMock(return_value=mock_backend)

        settings.CRAFTSMAN = {"DEMAND_BACKEND": "test.MockDemandBackend"}

        with patch("django.utils.module_loading.import_string", return_value=mock_backend_class):
            suggestions = craft.suggest(date(2026, 1, 14))

        # waste_rate=0.10 ≤ 0.15 → no adjustment; avg=100, quantity=100*1.2=120
        assert suggestions[0].quantity == Decimal("120")

    def test_suggest_high_demand_friday(self, settings):
        """High demand multiplier applied on Friday."""
        from unittest.mock import MagicMock, patch

        from shopman.craftsman.protocols.demand import DailyDemand
        from shopman.craftsman.models import Recipe

        friday = date(2026, 2, 27)  # weekday() == 4
        assert friday.weekday() == 4

        recipe_fri = Recipe.objects.create(
            code="croissant-fri", name="Croissant Fri", output_ref="croissant-fri",
            batch_size=Decimal("10"),
        )

        mock_backend = MagicMock()
        mock_backend.history.return_value = [
            DailyDemand(date=date(2025, 1, i + 1), sold=Decimal("100"), wasted=Decimal("0"))
            for i in range(5)
        ]
        mock_backend.committed.return_value = Decimal("0")
        mock_backend_class = MagicMock(return_value=mock_backend)

        settings.CRAFTSMAN = {"DEMAND_BACKEND": "test.MockDemandBackend"}

        with patch("django.utils.module_loading.import_string", return_value=mock_backend_class):
            suggestions = craft.suggest(friday, high_demand_multiplier=Decimal("1.5"))

        s = next(sg for sg in suggestions if sg.recipe.output_ref == "croissant-fri")
        # avg=100, safety=20% => 100*1.2=120, then *1.5 = 180
        assert s.basis["high_demand_applied"] is True
        assert s.quantity == Decimal("180")

    def test_suggest_high_demand_not_applied_on_weekday(self, recipe, tomorrow, settings):
        """High demand multiplier NOT applied on non-Fri/Sat day."""
        from unittest.mock import MagicMock, patch

        from shopman.craftsman.protocols.demand import DailyDemand

        # tomorrow fixture is 2026-02-25 (Wednesday)
        assert tomorrow.weekday() not in (4, 5)

        mock_backend = MagicMock()
        mock_backend.history.return_value = [
            DailyDemand(date=date(2025, 1, i + 1), sold=Decimal("100"), wasted=Decimal("0"))
            for i in range(5)
        ]
        mock_backend.committed.return_value = Decimal("0")
        mock_backend_class = MagicMock(return_value=mock_backend)

        settings.CRAFTSMAN = {"DEMAND_BACKEND": "test.MockDemandBackend"}

        with patch("django.utils.module_loading.import_string", return_value=mock_backend_class):
            suggestions = craft.suggest(tomorrow, high_demand_multiplier=Decimal("1.5"))

        assert suggestions[0].basis["high_demand_applied"] is False
        # No multiplier: avg=100, safety=20% => 120
        assert suggestions[0].quantity == Decimal("120")


# ══════════════════════════════════════════════════════════════
# ADJUST VALIDATIONS (WP-A8)
# ══════════════════════════════════════════════════════════════


class TestAdjustValidations:
    """Tests for WP-A8 adjust() validations: committed holds, shared ingredients, downstream."""

    def test_adjust_no_backend_skips_validation(self, recipe_with_items, tomorrow):
        """Without DEMAND_BACKEND or INVENTORY_BACKEND, adjust succeeds normally."""
        wo = craft.plan(recipe_with_items, 100, date=tomorrow)
        craft.adjust(wo, quantity=50)
        wo.refresh_from_db()
        assert wo.quantity == Decimal("50")

    def test_adjust_below_committed_holds(self, recipe, tomorrow, settings):
        """adjust() below committed quantity raises COMMITTED_HOLDS."""
        from unittest.mock import MagicMock, patch

        mock_backend = MagicMock()
        mock_backend.committed.return_value = Decimal("80")
        mock_backend_class = MagicMock(return_value=mock_backend)

        settings.CRAFTSMAN = {"DEMAND_BACKEND": "test.MockDemandBackend"}

        wo = craft.plan(recipe, 100, date=tomorrow)

        with patch("django.utils.module_loading.import_string", return_value=mock_backend_class):
            with pytest.raises(CraftError) as exc:
                craft.adjust(wo, quantity=50)

        assert exc.value.code == "COMMITTED_HOLDS"
        assert exc.value.data["committed"] == 80.0
        assert exc.value.data["requested"] == 50.0

    def test_adjust_at_committed_quantity_succeeds(self, recipe, tomorrow, settings):
        """adjust() exactly at committed quantity is allowed."""
        from unittest.mock import MagicMock, patch

        mock_backend = MagicMock()
        mock_backend.committed.return_value = Decimal("80")
        mock_backend_class = MagicMock(return_value=mock_backend)

        settings.CRAFTSMAN = {"DEMAND_BACKEND": "test.MockDemandBackend"}

        wo = craft.plan(recipe, 100, date=tomorrow)

        with patch("django.utils.module_loading.import_string", return_value=mock_backend_class):
            craft.adjust(wo, quantity=80)

        wo.refresh_from_db()
        assert wo.quantity == Decimal("80")

    def test_adjust_exceeds_shared_ingredient(self, recipe_with_items, tomorrow, settings):
        """adjust() raises INSUFFICIENT_MATERIALS when shared ingredients are short."""
        from unittest.mock import MagicMock, patch
        from shopman.craftsman.protocols.inventory import AvailabilityResult, MaterialStatus

        mock_inv = MagicMock()
        # Available farinha=20kg, but new WO needs 50kg (coefficient=100/10=10, farinha=5*10=50)
        mock_inv.available.return_value = AvailabilityResult(
            all_available=False,
            materials=[
                MaterialStatus(sku="farinha", needed=Decimal("50"), available=Decimal("20")),
            ],
        )
        mock_inv_class = MagicMock(return_value=mock_inv)

        settings.CRAFTSMAN = {"INVENTORY_BACKEND": "test.MockInvBackend"}

        wo = craft.plan(recipe_with_items, 50, date=tomorrow)

        with patch("django.utils.module_loading.import_string", return_value=mock_inv_class):
            with pytest.raises(CraftError) as exc:
                craft.adjust(wo, quantity=100)

        assert exc.value.code == "INSUFFICIENT_MATERIALS"
        shortages = exc.value.data["shortages"]
        assert any(s["sku"] == "farinha" for s in shortages)

    def test_adjust_within_limits_succeeds(self, recipe_with_items, tomorrow, settings):
        """adjust() within available ingredients succeeds."""
        from unittest.mock import MagicMock, patch
        from shopman.craftsman.protocols.inventory import AvailabilityResult, MaterialStatus

        mock_inv = MagicMock()
        mock_inv.available.return_value = AvailabilityResult(
            all_available=True,
            materials=[
                MaterialStatus(sku="farinha", needed=Decimal("50"), available=Decimal("100")),
            ],
        )
        mock_inv_class = MagicMock(return_value=mock_inv)

        settings.CRAFTSMAN = {"INVENTORY_BACKEND": "test.MockInvBackend"}

        wo = craft.plan(recipe_with_items, 50, date=tomorrow)

        with patch("django.utils.module_loading.import_string", return_value=mock_inv_class):
            craft.adjust(wo, quantity=80)

        wo.refresh_from_db()
        assert wo.quantity == Decimal("80")

    def test_adjust_to_zero_voids(self, recipe, tomorrow):
        """adjust(quantity=0) delegates to void()."""
        wo = craft.plan(recipe, 100, date=tomorrow)
        result = craft.adjust(wo, quantity=0)
        result.refresh_from_db()
        assert result.status == WorkOrder.Status.VOID

    def test_adjust_downstream_deficit_blocked(self, recipe, recipe_with_items, tomorrow):
        """Reducing a WO whose output is used by another WO raises DOWNSTREAM_DEFICIT."""
        # recipe_with_items uses: farinha, agua, fermento
        # We create a sub-recipe where "croissant" (output of recipe) is an ingredient
        intermediate = Recipe.objects.create(
            code="pain-complet",
            name="Pain Complet",
            output_ref="pain-complet",
            batch_size=Decimal("10"),
        )
        RecipeItem.objects.create(
            recipe=intermediate,
            input_ref="croissant",  # uses croissant output
            quantity=Decimal("2"),
            unit="un",
        )

        # Plan croissant WO (recipe output_ref="croissant")
        wo_croissant = craft.plan(recipe, 100, date=tomorrow)
        # Plan downstream WO that needs croissant as ingredient
        craft.plan(intermediate, 50, date=tomorrow)

        # Reducing croissant below downstream needs should raise DOWNSTREAM_DEFICIT
        with pytest.raises(CraftError) as exc:
            craft.adjust(wo_croissant, quantity=5, force=False)

        assert exc.value.code == "DOWNSTREAM_DEFICIT"

    def test_adjust_downstream_deficit_forced(self, recipe, tomorrow):
        """force=True allows adjusting despite downstream deficit (with warning)."""
        intermediate = Recipe.objects.create(
            code="pain-complet-force",
            name="Pain Complet Force",
            output_ref="pain-complet-force",
            batch_size=Decimal("10"),
        )
        RecipeItem.objects.create(
            recipe=intermediate,
            input_ref="croissant",
            quantity=Decimal("5"),
            unit="un",
        )

        wo_croissant = craft.plan(recipe, 100, date=tomorrow)
        craft.plan(intermediate, 50, date=tomorrow)

        # force=True: should succeed despite deficit
        craft.adjust(wo_croissant, quantity=5, force=True)
        wo_croissant.refresh_from_db()
        assert wo_croissant.quantity == Decimal("5")
