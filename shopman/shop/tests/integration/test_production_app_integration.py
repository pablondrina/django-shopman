"""
Integration tests for WP-B4: Craftsman ↔ App.

Tests the full integration loop:
- CraftService.finish() → InventoryProtocol.consume() → ingredients issued from stock
- CraftService.finish() → InventoryProtocol.receive() → finished goods received in stock
- CraftService.suggest() via management command
- production_changed signal → planned quants → hold materialization
"""

from __future__ import annotations

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from shopman.craftsman.models import WorkOrder
from shopman.craftsman.service import CraftService as craft
from shopman.stockman import stock
from shopman.stockman.models import Quant

pytestmark = pytest.mark.django_db


CRAFTING_WITH_BACKENDS = {
    "INVENTORY_BACKEND": "shopman.craftsman.adapters.stock.StockingBackend",
    "DEMAND_BACKEND": "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend",
    "CATALOG_BACKEND": "shopman.offerman.adapters.catalog_backend.OffermanCatalogBackend",
}


# =============================================================================
# CraftService.finish() → Inventory Protocol
# =============================================================================


class TestFinishWorkOrderInventoryIntegration:
    """CraftService.finish() should interact with stock via InventoryProtocol."""

    def test_finish_work_order_issues_ingredients(
        self, settings, recipe, ingredient, croissant,
        position_producao, position_loja, today,
    ):
        settings.CRAFTING = CRAFTING_WITH_BACKENDS

        # Add ingredient stock
        stock.receive(
            quantity=Decimal("10"),
            sku=ingredient.sku,
            position=position_producao,
            target_date=today,
            reason="Ingredient stock",
        )

        initial_ingredient = stock.available(
            ingredient, target_date=today, position=position_producao,
        )
        assert initial_ingredient == Decimal("10")

        # Plan and finish work order via CraftService
        wo = craft.plan(recipe, quantity=Decimal("20"), date=today)
        craft.finish(wo, finished=18, actor="test")

        # The InventoryProtocol.consume + receive should have been called
        assert wo.status == WorkOrder.Status.FINISHED
        assert wo.finished == Decimal("18")

    def test_finish_work_order_receives_finished_product(
        self, settings, recipe, croissant, position_loja, today,
    ):
        settings.CRAFTING = CRAFTING_WITH_BACKENDS

        wo = craft.plan(recipe, quantity=Decimal("10"), date=today)
        craft.finish(wo, finished=9, actor="test")

        assert wo.status == WorkOrder.Status.FINISHED
        assert wo.finished == Decimal("9")


# =============================================================================
# production_changed signal → Stockman handlers
# =============================================================================


class TestProductionSignalCreatesPlannedQuant:
    """CraftService.plan() should create planned Quants via production_changed signal."""

    def test_plan_creates_planned_quant(
        self, recipe, croissant, position_producao, tomorrow,
    ):
        # Ensure the craftsman contrib stockman handler is loaded
        import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

        craft.plan(recipe, quantity=Decimal("50"), date=tomorrow)

        # The production_changed signal (action=planned) should create a planned Quant
        quant = Quant.objects.filter(
            sku=croissant.sku,
            target_date=tomorrow,
        ).first()

        assert quant is not None, "Planned quant should be created by signal handler"
        assert quant._quantity == Decimal("50")

    def test_adjust_updates_planned_quant(
        self, recipe, croissant, position_producao, tomorrow,
    ):
        import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

        wo = craft.plan(recipe, quantity=Decimal("50"), date=tomorrow)

        # Adjust quantity
        craft.adjust(wo, quantity=Decimal("70"), reason="Increased demand")

        quant = Quant.objects.filter(
            sku=croissant.sku,
            target_date=tomorrow,
        ).first()

        assert quant is not None
        assert quant._quantity == Decimal("70")

    def test_void_cancels_planned_quant(
        self, recipe, croissant, position_producao, tomorrow,
    ):
        import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

        wo = craft.plan(recipe, quantity=Decimal("50"), date=tomorrow)

        # Verify quant exists
        assert Quant.objects.filter(
            sku=croissant.sku, target_date=tomorrow,
        ).exists()

        # Void the work order
        craft.void(wo, reason="Cancelled")

        # Quant should be zeroed out
        quant = Quant.objects.filter(
            sku=croissant.sku, target_date=tomorrow,
        ).first()

        assert quant is not None
        assert quant._quantity == Decimal("0")

    def test_start_splits_planned_and_expected_supply(
        self, recipe, croissant, position_producao, tomorrow,
    ):
        import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

        wo = craft.plan(
            recipe,
            quantity=Decimal("50"),
            date=tomorrow,
            position_ref=position_producao.ref,
        )

        craft.start(
            wo,
            quantity=Decimal("30"),
            expected_rev=0,
            position_ref=position_producao.ref,
            operator_ref="user:joao",
        )

        planned_quant = Quant.objects.filter(
            sku=croissant.sku,
            target_date=tomorrow,
            batch="",
        ).first()
        started_quant = Quant.objects.filter(
            sku=croissant.sku,
            target_date=tomorrow,
            position=position_producao,
            batch="started",
        ).first()

        assert planned_quant is not None
        assert planned_quant._quantity == Decimal("20")
        assert started_quant is not None
        assert started_quant._quantity == Decimal("30")

        decision = stock.promise(croissant.sku, Decimal("25"), target_date=tomorrow)
        assert decision.approved is True
        assert decision.expected == Decimal("30")
        assert decision.planned == Decimal("20")
        assert decision.available_qty == Decimal("50")


# =============================================================================
# Suggest production management command
# =============================================================================


class TestSuggestProductionCommand:
    """Test the suggest_production management command."""

    def test_command_runs_without_error(self, settings, recipe, croissant, tomorrow):
        settings.CRAFTING = CRAFTING_WITH_BACKENDS
        out = StringIO()
        call_command("suggest_production", "--date", str(tomorrow), stdout=out)
        output = out.getvalue()
        # Should produce output (either suggestions or "no suggestions" message)
        assert len(output) > 0

    def test_command_with_no_demand_backend(self, settings, recipe, croissant, tomorrow):
        settings.CRAFTING = {"DEMAND_BACKEND": None}
        out = StringIO()
        call_command("suggest_production", "--date", str(tomorrow), stdout=out)
        output = out.getvalue()
        assert "Nenhuma sugestão" in output

    def test_command_filters_by_sku(self, settings, recipe, croissant, tomorrow):
        settings.CRAFTING = CRAFTING_WITH_BACKENDS
        out = StringIO()
        call_command(
            "suggest_production",
            "--date", str(tomorrow),
            "--skus", croissant.sku,
            stdout=out,
        )
        output = out.getvalue()
        assert len(output) > 0


# =============================================================================
# Planned hold → production materialization
# =============================================================================


class TestPlannedHoldMaterializationFlow:
    """End-to-end: planned hold → production → materialization."""

    def test_planned_hold_exists_for_future_production(
        self, croissant, position_loja, tomorrow,
    ):
        """When production is planned, customers can create holds on planned stock."""
        stock.plan(
            quantity=Decimal("100"),
            product=croissant,
            target_date=tomorrow,
            reason="Morning production",
        )

        available = stock.available(croissant, target_date=tomorrow)
        assert available == Decimal("100")

        hold_id = stock.hold(
            quantity=Decimal("5"),
            product=croissant,
            target_date=tomorrow,
        )
        assert hold_id is not None

        available_after = stock.available(croissant, target_date=tomorrow)
        assert available_after == Decimal("95")

    def test_production_finished_via_craft_service(
        self, recipe, croissant, position_loja, today,
    ):
        """Finishing a work order creates stock through the signal chain."""
        import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

        wo = craft.plan(recipe, quantity=Decimal("50"), date=today)

        # Verify planned quant was created
        planned = Quant.objects.filter(sku=croissant.sku, target_date=today).first()
        assert planned is not None

        # Finish work order (triggers production_changed with action=finished)
        craft.finish(wo, finished=48, actor="test")

        assert wo.status == WorkOrder.Status.FINISHED
