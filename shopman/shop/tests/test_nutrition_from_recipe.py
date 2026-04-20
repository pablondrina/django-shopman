"""Tests for shopman.shop.services.nutrition_from_recipe.

Covers:
- Signal wires Recipe → Product nutrition + ingredients.
- ``auto_filled=False`` on Product blocks overwrite.
- Bundles are skipped.
- Empty Recipe (no items) is a no-op.
- RecipeItem without ``meta["nutrition"]`` still contributes to
  ingredients_text but not to the nutritional sum.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.offerman.models import Product, ProductComponent

from shopman.shop.services.nutrition_from_recipe import fill_nutrition_from_recipe

pytestmark = pytest.mark.django_db


def _make_product(sku: str = "PAO", unit_weight_g: int = 50, **extra) -> Product:
    return Product.objects.create(
        sku=sku,
        name="Pão de Teste",
        base_price_q=500,
        unit_weight_g=unit_weight_g,
        **extra,
    )


def _make_recipe_with_items(sku: str = "PAO", batch_size: Decimal = Decimal("10")) -> Recipe:
    recipe = Recipe.objects.create(
        ref=f"{sku.lower()}-v1",
        name=f"Receita {sku}",
        output_ref=sku,
        batch_size=batch_size,
        is_active=True,
    )
    # 1 kg farinha, 650 g água, 10 g sal → for a batch of 10 units.
    RecipeItem.objects.create(
        recipe=recipe,
        input_ref="FARINHA",
        quantity=Decimal("1.000"),
        meta={
            "label": "Farinha de trigo",
            "nutrition": {
                "energy_kcal": 364, "carbohydrates_g": 76, "sugars_g": 0.3,
                "proteins_g": 10, "total_fat_g": 1.0, "saturated_fat_g": 0.2,
                "trans_fat_g": 0, "fiber_g": 2.7, "sodium_mg": 2,
            },
        },
    )
    RecipeItem.objects.create(
        recipe=recipe,
        input_ref="AGUA",
        quantity=Decimal("0.650"),
        meta={"label": "Água", "nutrition": {"energy_kcal": 0}},
    )
    RecipeItem.objects.create(
        recipe=recipe,
        input_ref="SAL",
        quantity=Decimal("0.010"),
        meta={
            "label": "Sal",
            "nutrition": {"sodium_mg": 38758, "energy_kcal": 0},
        },
    )
    return recipe


class TestFillNutritionFromRecipe:
    def test_fills_when_no_prior_override(self):
        product = _make_product()
        _make_recipe_with_items()

        changed = fill_nutrition_from_recipe(product)
        product.refresh_from_db()

        assert changed is True
        assert product.nutrition_facts
        assert product.nutrition_facts.get("auto_filled") is True
        assert product.ingredients_text.startswith("Farinha de trigo")
        # Per unit: (1.000 kg / 10 units) * 1000 = 100 g flour
        # Energy: 100 g * (364 kcal / 100 g) = 364 kcal per unit
        assert product.nutrition_facts["energy_kcal"] == pytest.approx(364.0, abs=2.0)

    def test_ingredients_text_in_decreasing_weight_order(self):
        product = _make_product()
        _make_recipe_with_items()
        fill_nutrition_from_recipe(product)
        product.refresh_from_db()

        # Order: FARINHA (1.000) > AGUA (0.650) > SAL (0.010)
        text = product.ingredients_text
        assert text.index("Farinha") < text.index("Água") < text.index("Sal")

    def test_manual_override_is_not_clobbered(self):
        product = _make_product()
        product.nutrition_facts = {
            "serving_size_g": 100,
            "energy_kcal": 999.0,
            "auto_filled": False,
        }
        product.save(update_fields=["nutrition_facts"])
        _make_recipe_with_items()

        changed = fill_nutrition_from_recipe(product)
        product.refresh_from_db()

        assert changed is False
        assert product.nutrition_facts["energy_kcal"] == 999.0
        assert product.nutrition_facts["auto_filled"] is False

    def test_bundle_is_skipped(self):
        child = _make_product(sku="PAO-SIMPLES")
        bundle = _make_product(sku="COMBO")
        ProductComponent.objects.create(parent=bundle, component=child, qty=Decimal("1"))
        _make_recipe_with_items(sku="COMBO")

        changed = fill_nutrition_from_recipe(bundle)
        bundle.refresh_from_db()

        assert changed is False
        assert bundle.nutrition_facts == {} or not bundle.nutrition_facts

    def test_no_recipe_is_noop(self):
        product = _make_product(sku="REVENDIDO")
        changed = fill_nutrition_from_recipe(product)
        product.refresh_from_db()
        assert changed is False
        assert not product.nutrition_facts
        assert product.ingredients_text == ""

    def test_recipe_without_nutrition_meta_fills_only_ingredients(self):
        product = _make_product(sku="PAOSIMPLES")
        recipe = Recipe.objects.create(
            ref="paosimples-v1",
            name="Simples",
            output_ref="PAOSIMPLES",
            batch_size=Decimal("5"),
            is_active=True,
        )
        RecipeItem.objects.create(
            recipe=recipe, input_ref="FARINHA", quantity=Decimal("1.0"),
            meta={"label": "Farinha"},
        )

        fill_nutrition_from_recipe(product)
        product.refresh_from_db()

        assert product.ingredients_text == "Farinha."
        # No nutrition profile → nutrition_facts stays empty
        assert not product.nutrition_facts

    def test_inactive_recipe_is_ignored(self):
        product = _make_product()
        recipe = _make_recipe_with_items()
        recipe.is_active = False
        recipe.save()

        changed = fill_nutrition_from_recipe(product)
        product.refresh_from_db()
        assert changed is False
        assert not product.nutrition_facts


class TestRecipeSignal:
    """Verify that the post_save signal on Recipe triggers derivation."""

    def test_saving_recipe_materializes_on_product(self):
        product = _make_product(sku="PAO-SIGNAL")
        recipe = Recipe.objects.create(
            ref="pao-signal-v1",
            name="Signal Test",
            output_ref="PAO-SIGNAL",
            batch_size=Decimal("10"),
            is_active=True,
        )
        RecipeItem.objects.create(
            recipe=recipe,
            input_ref="FARINHA",
            quantity=Decimal("1.000"),
            meta={
                "label": "Farinha",
                "nutrition": {"energy_kcal": 364, "proteins_g": 10},
            },
        )
        # Touch the recipe to fire the signal after items exist.
        recipe.save()

        product.refresh_from_db()
        assert "Farinha" in (product.ingredients_text or "")
        assert product.nutrition_facts.get("auto_filled") is True
