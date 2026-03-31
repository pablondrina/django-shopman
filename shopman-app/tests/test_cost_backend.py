"""Tests for CraftingCostBackend."""

from decimal import Decimal

import pytest
from shopman.crafting.models import Recipe, RecipeItem

from channels.backends.cost import CraftingCostBackend


@pytest.fixture
def backend():
    return CraftingCostBackend()


@pytest.fixture
def recipe_with_costs(db):
    """Recipe where all items have unit_cost_q in meta."""
    recipe = Recipe.objects.create(
        code="croissant-v1",
        name="Croissant",
        output_ref="CROISSANT",
        batch_size=Decimal("10"),
    )
    # Farinha: 2kg @ 500 centavos/kg = 1000
    RecipeItem.objects.create(
        recipe=recipe,
        input_ref="FARINHA",
        quantity=Decimal("2"),
        unit="kg",
        meta={"unit_cost_q": 500},
    )
    # Manteiga: 1kg @ 3000 centavos/kg = 3000
    RecipeItem.objects.create(
        recipe=recipe,
        input_ref="MANTEIGA",
        quantity=Decimal("1"),
        unit="kg",
        meta={"unit_cost_q": 3000},
    )
    return recipe


@pytest.fixture
def recipe_no_costs(db):
    """Recipe where no items have cost data."""
    recipe = Recipe.objects.create(
        code="baguete-v1",
        name="Baguete",
        output_ref="BAGUETE",
        batch_size=Decimal("5"),
    )
    RecipeItem.objects.create(
        recipe=recipe,
        input_ref="FARINHA",
        quantity=Decimal("3"),
        unit="kg",
    )
    return recipe


@pytest.fixture
def recipe_partial_costs(db):
    """Recipe where some items have cost data."""
    recipe = Recipe.objects.create(
        code="brioche-v1",
        name="Brioche",
        output_ref="BRIOCHE",
        batch_size=Decimal("5"),
    )
    RecipeItem.objects.create(
        recipe=recipe,
        input_ref="FARINHA",
        quantity=Decimal("1"),
        unit="kg",
        meta={"unit_cost_q": 500},
    )
    RecipeItem.objects.create(
        recipe=recipe,
        input_ref="OVO",
        quantity=Decimal("6"),
        unit="un",
        meta={},  # no cost
    )
    return recipe


@pytest.mark.django_db
class TestCraftingCostBackend:
    def test_get_cost_with_full_data(self, backend, recipe_with_costs):
        # Total: (2 * 500) + (1 * 3000) = 4000 centavos
        # Per unit: 4000 / 10 = 400 centavos
        cost = backend.get_cost("CROISSANT")
        assert cost == 400

    def test_get_cost_unknown_sku(self, backend, db):
        assert backend.get_cost("INEXISTENTE") is None

    def test_get_cost_no_cost_data(self, backend, recipe_no_costs):
        assert backend.get_cost("BAGUETE") is None

    def test_get_cost_partial_data(self, backend, recipe_partial_costs):
        # Only farinha: 1 * 500 = 500 / 5 = 100
        cost = backend.get_cost("BRIOCHE")
        assert cost == 100

    def test_get_cost_inactive_recipe(self, backend, recipe_with_costs):
        recipe_with_costs.is_active = False
        recipe_with_costs.save()
        assert backend.get_cost("CROISSANT") is None

    def test_protocol_compliance(self, backend):
        from shopman.offering.protocols.cost import CostBackend

        assert isinstance(backend, CostBackend)

    def test_get_cost_rounding(self, backend, db):
        """Cost rounds to nearest centavo."""
        recipe = Recipe.objects.create(
            code="pao-v1",
            name="Pão",
            output_ref="PAO",
            batch_size=Decimal("3"),
        )
        RecipeItem.objects.create(
            recipe=recipe,
            input_ref="FARINHA",
            quantity=Decimal("1"),
            unit="kg",
            meta={"unit_cost_q": 100},
        )
        # 100 / 3 = 33.33... → 33
        cost = backend.get_cost("PAO")
        assert cost == 33
