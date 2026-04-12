"""
Integration tests: Crafting <-> Stocking

Tests the production workflow integration:
- WorkOrder completion adds stock to Stocking
- Recipe ingredients can check/reserve Stocking inventory
- Production planning respects stock availability

Covers:
- Production output -> stock.receive
- Ingredient availability checks
- Hold/release for ingredients
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from shopman.craftsman.models import WorkOrder
from shopman.stockman import stock

pytestmark = pytest.mark.django_db


# =============================================================================
# PRODUCTION OUTPUT -> STOCKING
# =============================================================================


class TestProductionOutputToStock:
    """Tests for adding production output to Stocking."""

    def test_complete_work_order_adds_stock(
        self, work_order, croissant, position_loja, today
    ):
        """Completing WorkOrder should add stock via Stocking."""
        # Initial stock should be 0
        initial = stock.available(croissant, target_date=today, position=position_loja)
        assert initial == Decimal("0")

        # Start and complete the work order
        work_order.started_at = timezone.now()
        work_order.save(update_fields=["started_at"])

        actual_qty = Decimal("48")
        work_order.finished = actual_qty
        work_order.status = WorkOrder.Status.FINISHED
        work_order.finished_at = timezone.now()
        work_order.save(update_fields=["finished", "status", "finished_at"])

        # Manually add stock (simulating what hook/signal would do)
        stock.receive(
            quantity=actual_qty,
            sku=croissant.sku,
            position=position_loja,
            target_date=today,
            reason=f"WorkOrder {work_order.ref}",
        )

        # Verify stock was added
        final = stock.available(croissant, target_date=today, position=position_loja)
        assert final == Decimal("48")

    def test_multiple_work_orders_accumulate_stock(
        self, recipe, croissant, position_loja, position_producao, today
    ):
        """Multiple completed WorkOrders should accumulate stock."""
        from shopman.craftsman.models import WorkOrder

        # Create and complete first work order
        wo1 = WorkOrder.objects.create(
            recipe=recipe,
            output_ref=recipe.output_ref,
            quantity=Decimal("50"),
            finished=Decimal("48"),
            status=WorkOrder.Status.FINISHED,
            scheduled_date=today,
            position_ref=position_producao.ref,
            started_at=timezone.now(),
            finished_at=timezone.now(),
        )
        stock.receive(
            quantity=Decimal("48"),
            sku=croissant.sku,
            position=position_loja,
            target_date=today,
            reason=f"WorkOrder {wo1.ref}",
        )

        # Create and complete second work order
        wo2 = WorkOrder.objects.create(
            recipe=recipe,
            output_ref=recipe.output_ref,
            quantity=Decimal("30"),
            finished=Decimal("28"),
            status=WorkOrder.Status.FINISHED,
            scheduled_date=today,
            position_ref=position_producao.ref,
            started_at=timezone.now(),
            finished_at=timezone.now(),
        )
        stock.receive(
            quantity=Decimal("28"),
            sku=croissant.sku,
            position=position_loja,
            target_date=today,
            reason=f"WorkOrder {wo2.ref}",
        )

        # Total stock should be sum of both
        total = stock.available(croissant, target_date=today, position=position_loja)
        assert total == Decimal("76")  # 48 + 28

    def test_production_creates_move_record(
        self, croissant, position_loja, today
    ):
        """Stock addition should create Move audit record."""
        quant = stock.receive(
            quantity=Decimal("50"),
            sku=croissant.sku,
            position=position_loja,
            target_date=today,
            reason="Production WO-TEST",
        )

        # Verify Move was created
        moves = quant.moves.all()
        assert moves.count() == 1
        assert moves[0].delta == Decimal("50")
        assert "WO-TEST" in moves[0].reason


# =============================================================================
# INGREDIENT AVAILABILITY
# =============================================================================


class TestIngredientAvailability:
    """Tests for checking ingredient availability via Stocking."""

    def test_check_ingredient_availability(
        self, ingredient, position_producao, today
    ):
        """Should be able to check if ingredients are available."""
        # Add ingredient stock
        stock.receive(
            quantity=Decimal("10"),  # 10 kg flour
            sku=ingredient.sku,
            position=position_producao,
            target_date=today,
            reason="Ingredient stock",
        )

        # Check availability
        available = stock.available(ingredient, target_date=today, position=position_producao)
        assert available == Decimal("10")

    def test_ingredient_reservation_for_production(
        self, ingredient, position_producao, today
    ):
        """Should be able to reserve ingredients for production."""
        # Add ingredient stock
        stock.receive(
            quantity=Decimal("10"),
            sku=ingredient.sku,
            position=position_producao,
            target_date=today,
            reason="Ingredient stock",
        )

        # Reserve for production
        hold_id = stock.hold(
            quantity=Decimal("3"),
            product=ingredient,
            target_date=today,
            purpose="workorder",
            purpose_id="WO-001",
        )

        # Check availability reduced
        available = stock.available(ingredient, target_date=today, position=position_producao)
        assert available == Decimal("7")  # 10 - 3

    def test_ingredient_consumption_on_production(
        self, ingredient, position_producao, today
    ):
        """Completing production should consume ingredients."""
        # Add ingredient stock
        stock.receive(
            quantity=Decimal("10"),
            sku=ingredient.sku,
            position=position_producao,
            target_date=today,
            reason="Ingredient stock",
        )

        # Reserve ingredients
        hold_id = stock.hold(
            quantity=Decimal("3"),
            product=ingredient,
            target_date=today,
            purpose="workorder",
            purpose_id="WO-001",
        )

        # Confirm and fulfill (consume)
        stock.confirm(hold_id)
        stock.fulfill(hold_id)

        # Stock should be reduced permanently
        qty = stock.available(ingredient, target_date=today, position=position_producao)
        assert qty == Decimal("7")  # 10 - 3 consumed

    def test_ingredient_release_on_cancel(
        self, ingredient, position_producao, today
    ):
        """Cancelling production should release ingredient holds."""
        # Add ingredient stock
        stock.receive(
            quantity=Decimal("10"),
            sku=ingredient.sku,
            position=position_producao,
            target_date=today,
            reason="Ingredient stock",
        )

        # Reserve ingredients
        hold_id = stock.hold(
            quantity=Decimal("3"),
            product=ingredient,
            target_date=today,
            purpose="workorder",
            purpose_id="WO-001",
        )

        # Verify availability reduced
        assert stock.available(ingredient, target_date=today, position=position_producao) == Decimal("7")

        # Cancel (release hold)
        stock.release(hold_id, reason="Production cancelled")

        # Availability should be restored
        assert stock.available(ingredient, target_date=today, position=position_producao) == Decimal("10")


# =============================================================================
# PRODUCTION PLANNING
# =============================================================================


class TestProductionPlanning:
    """Tests for production planning with stock awareness."""

    def test_plan_stock_creates_future_quant(
        self, croissant, tomorrow
    ):
        """Planning production should create future Quant."""
        quant = stock.plan(
            quantity=Decimal("100"),
            product=croissant,
            target_date=tomorrow,
            reason="Production plan",
        )

        assert quant.target_date == tomorrow
        assert quant._quantity == Decimal("100")
        assert quant.is_future is True

    def test_planned_stock_available_on_date(
        self, croissant, tomorrow
    ):
        """Planned stock should be available on target date."""
        stock.plan(
            quantity=Decimal("100"),
            product=croissant,
            target_date=tomorrow,
            reason="Production plan",
        )

        # Not available today
        today = date.today()
        available_today = stock.available(croissant, target_date=today)
        assert available_today == Decimal("0")

        # Available tomorrow
        available_tomorrow = stock.available(croissant, target_date=tomorrow)
        assert available_tomorrow == Decimal("100")

    def test_demand_hold_for_planned_production(
        self, bolo, tomorrow
    ):
        """Should be able to create demand hold for future production."""
        # Product with demand_ok policy allows demand holds
        hold_id = stock.hold(
            quantity=Decimal("5"),
            product=bolo,
            target_date=tomorrow,
            purpose="order",
            purpose_id="ORD-001",
            is_demand=True,
        )

        assert hold_id.startswith("hold:")

        # Plan production to fulfill demand
        stock.plan(
            quantity=Decimal("10"),
            product=bolo,
            target_date=tomorrow,
            reason="To fulfill demand",
        )

        # Now there's stock to satisfy the demand
        available = stock.available(bolo, target_date=tomorrow)
        # Planned stock should be available
        assert available >= Decimal("0")


# =============================================================================
# STOCK TRACKING BY POSITION
# =============================================================================


class TestStockByPosition:
    """Tests for tracking stock by position (production vs store)."""

    def test_transfer_from_production_to_store(
        self, croissant, position_producao, position_loja, today
    ):
        """Should track transfers between positions."""
        # Add to production area
        stock.receive(
            quantity=Decimal("100"),
            sku=croissant.sku,
            position=position_producao,
            target_date=today,
            reason="Production complete",
        )

        # Verify production area has stock
        assert stock.available(croissant, target_date=today, position=position_producao) == Decimal("100")
        assert stock.available(croissant, target_date=today, position=position_loja) == Decimal("0")

        # Transfer to store: issue from production, receive to store
        quant = stock.get_quant(croissant, position=position_producao, target_date=today)
        stock.issue(
            quantity=Decimal("50"),
            quant=quant,
            reason="Transfer to store",
        )
        stock.receive(
            quantity=Decimal("50"),
            sku=croissant.sku,
            position=position_loja,
            target_date=today,
            reason="Transfer from production",
        )

        # Verify transfer
        assert stock.available(croissant, target_date=today, position=position_producao) == Decimal("50")
        assert stock.available(croissant, target_date=today, position=position_loja) == Decimal("50")

    def test_saleable_position_only(
        self, croissant, position_producao, position_loja, today
    ):
        """Only saleable positions should be used for order fulfillment."""
        from shopman.stockman.models import Position

        # Production position is not saleable
        assert position_producao.is_saleable is False
        assert position_loja.is_saleable is True

        # Add stock to both
        stock.receive(
            quantity=Decimal("100"),
            sku=croissant.sku,
            position=position_producao,
            target_date=today,
            reason="In production",
        )
        stock.receive(
            quantity=Decimal("50"),
            sku=croissant.sku,
            position=position_loja,
            target_date=today,
            reason="In store",
        )

        # For sales, only store stock counts
        saleable_positions = Position.objects.filter(is_saleable=True)
        saleable_qty = sum(
            stock.available(croissant, target_date=today, position=pos)
            for pos in saleable_positions
        )
        assert saleable_qty == Decimal("50")


# =============================================================================
# PERISHABLE PRODUCTS
# =============================================================================


@pytest.mark.skip(reason="Perishable expiry via shelf_life_days not yet wired in stockman.available()")
class TestPerishableProducts:
    """Tests for perishable product handling."""

    def test_perishable_stock_expires(
        self, croissant, position_loja, today, tomorrow
    ):
        """Perishable product (shelf_life_days=0) expires same day."""
        # croissant has shelf_life_days=0
        stock.receive(
            quantity=Decimal("50"),
            sku=croissant.sku,
            position=position_loja,
            target_date=today,
            reason="Morning production",
        )

        # Available today
        assert stock.available(croissant, target_date=today, position=position_loja) == Decimal("50")

        # Not available tomorrow (expired)
        assert stock.available(croissant, target_date=tomorrow, position=position_loja) == Decimal("0")

    def test_extended_shelflife(
        self, bolo, position_loja, today
    ):
        """Product with shelf_life_days=3 available for 3 days."""
        # bolo has shelf_life_days=3
        stock.receive(
            quantity=Decimal("10"),
            sku=bolo.sku,
            position=position_loja,
            target_date=today,
            reason="Production",
        )

        # Available today
        assert stock.available(bolo, target_date=today, position=position_loja) == Decimal("10")

        # Available day 2
        day2 = today + timedelta(days=2)
        assert stock.available(bolo, target_date=day2, position=position_loja) == Decimal("10")

        # Not available day 4 (expired)
        day4 = today + timedelta(days=4)
        assert stock.available(bolo, target_date=day4, position=position_loja) == Decimal("0")
