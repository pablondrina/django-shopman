from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder
from shopman.craftsman.protocols.demand import DailyDemand


@pytest.fixture
def recipe(db):
    recipe = Recipe.objects.create(
        ref="pao-frances-v1",
        name="Pao Frances",
        output_sku="PAO-FRANCES",
        batch_size=Decimal("10"),
    )
    RecipeItem.objects.create(
        recipe=recipe,
        input_sku="FARINHA",
        quantity=Decimal("5"),
        unit="kg",
    )
    return recipe


class FridayFactorProvider:
    def factors_for(self, *, date, output_sku, recipe, base_basis):
        return [{
            "ref": "weekday.friday",
            "kind": "multiplier",
            "value": "1.5",
            "reason": "sexta",
            "source": "test",
            "version": "1",
        }]


def test_formula_suggest_builds_basis_without_formula_plan(recipe, settings):
    from shopman.craftsman.contrib.formula import suggest

    target = date.today() + timedelta(days=1)
    settings.CRAFTSMAN = {
        "DEMAND_BACKEND": "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend",
        "FORMULA_FACTOR_PROVIDERS": [
            "shopman.craftsman.tests.test_formula.FridayFactorProvider",
        ],
        "FORMULA_ROUNDING_MULTIPLE": "5",
    }
    history = [
        DailyDemand(date=date.today() - timedelta(days=7), sold=Decimal("20"), wasted=Decimal("0")),
        DailyDemand(date=date.today() - timedelta(days=14), sold=Decimal("20"), wasted=Decimal("0")),
    ]
    with patch(
        "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend.history",
        return_value=history,
    ), patch(
        "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend.committed",
        return_value=Decimal("0"),
    ):
        lines = suggest(target)

    assert len(lines) == 1
    assert lines[0].basis["recipe_ref"] == "pao-frances-v1"
    assert lines[0].basis["factors"][0]["ref"] == "weekday.friday"
    assert lines[0].basis["material_availability"]["status"] == "unknown"
    assert "FormulaPlan" not in {model.__name__ for model in Recipe._meta.apps.get_models()}


def test_accept_suggestion_creates_work_order_with_formula_basis(recipe, settings):
    from shopman.craftsman.contrib.formula import accept_suggestion

    target = date.today() + timedelta(days=1)
    settings.CRAFTSMAN = {
        "DEMAND_BACKEND": "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend",
    }
    history = [
        DailyDemand(date=date.today() - timedelta(days=7), sold=Decimal("10"), wasted=Decimal("0")),
    ]
    with patch(
        "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend.history",
        return_value=history,
    ), patch(
        "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend.committed",
        return_value=Decimal("0"),
    ):
        order = accept_suggestion(
            recipe_ref=recipe.ref,
            target_date=target,
            actor="test:formula",
        )

    order.refresh_from_db()
    assert order.status == WorkOrder.Status.PLANNED
    assert order.source_ref == "formula:suggestion"
    assert order.meta["formula_basis"]["recipe_ref"] == recipe.ref
    assert Decimal(order.meta["formula_basis"]["accepted_quantity"]) == order.quantity
    assert order.events.filter(payload__reason="formula_accept").exists()
