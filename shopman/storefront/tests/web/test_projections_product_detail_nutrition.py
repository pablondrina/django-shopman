"""Tests for ``shopman.shop.projections.product_detail`` nutrition path.

Reuses the storefront web fixtures. Focused on:
- ``ingredients_text`` propagates to the projection.
- ``nutrition_facts`` becomes a typed ``NutritionFactsProjection``.
- %VD is computed for nutrients with ANVISA DRVs.
"""

from __future__ import annotations

import pytest
from shopman.offerman.models import ListingItem, Product

from shopman.storefront.projections.product_detail import (
    NutritionFactsProjection,
    build_product_detail,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def product_with_nutrition(listing):
    product = Product.objects.create(
        sku="CROISSANT",
        name="Croissant",
        base_price_q=1300,
        unit_weight_g=80,
        is_published=True,
        is_sellable=True,
        ingredients_text="Farinha de trigo, manteiga, leite, ovos, sal.",
        nutrition_facts={
            "serving_size_g": 80,
            "servings_per_container": 1,
            "energy_kcal": 320.0,
            "carbohydrates_g": 32.0,
            "sugars_g": 5.0,
            "proteins_g": 7.0,
            "total_fat_g": 18.0,
            "saturated_fat_g": 11.0,
            "trans_fat_g": 0.5,
            "fiber_g": 1.2,
            "sodium_mg": 480.0,
            "auto_filled": False,
        },
    )
    ListingItem.objects.create(
        listing=listing, product=product, price_q=1300,
        is_published=True, is_sellable=True,
    )
    return product


def test_projection_exposes_ingredients_text(product_with_nutrition):
    proj = build_product_detail(sku="CROISSANT", channel_ref="web")
    assert proj is not None
    assert proj.ingredients_text == "Farinha de trigo, manteiga, leite, ovos, sal."


def test_projection_exposes_typed_nutrition(product_with_nutrition):
    proj = build_product_detail(sku="CROISSANT", channel_ref="web")
    assert proj is not None
    assert isinstance(proj.nutrition, NutritionFactsProjection)
    assert proj.nutrition.has_any
    assert proj.nutrition.energy_kcal_display == "320"
    # 320 / 2000 * 100 = 16
    assert proj.nutrition.energy_pdv == 16
    assert proj.nutrition.serving_size_display == "80 g"


def test_projection_rows_ordered_and_formatted(product_with_nutrition):
    proj = build_product_detail(sku="CROISSANT", channel_ref="web")
    assert proj is not None
    labels = [row.field for row in proj.nutrition.rows]
    # Relative order defined by _NUTRIENT_ORDER
    assert labels.index("carbohydrates_g") < labels.index("sugars_g")
    assert labels.index("total_fat_g") < labels.index("saturated_fat_g")
    # Sodium should carry a %VD (480 / 2400 * 100 = 20)
    sodium_row = next(r for r in proj.nutrition.rows if r.field == "sodium_mg")
    assert sodium_row.percent_daily_value == 20
    assert sodium_row.unit == "mg"
    # Sugars has no ANVISA DRV → None
    sugars_row = next(r for r in proj.nutrition.rows if r.field == "sugars_g")
    assert sugars_row.percent_daily_value is None


def test_projection_hides_nutrition_when_empty(listing):
    product = Product.objects.create(
        sku="SIMPLES",
        name="Simples",
        base_price_q=500,
        is_published=True,
        is_sellable=True,
    )
    ListingItem.objects.create(
        listing=listing, product=product, price_q=500,
        is_published=True, is_sellable=True,
    )
    proj = build_product_detail(sku="SIMPLES", channel_ref="web")
    assert proj is not None
    assert proj.ingredients_text is None
    assert proj.nutrition is None


def test_projection_hides_nutrition_when_only_serving_size(listing):
    """``has_any_nutrient`` is False when no nutrient is set."""
    product = Product.objects.create(
        sku="ONLY-SIZE",
        name="Só Porção",
        base_price_q=500,
        is_published=True,
        is_sellable=True,
        nutrition_facts={"serving_size_g": 50, "auto_filled": False},
    )
    ListingItem.objects.create(
        listing=listing, product=product, price_q=500,
        is_published=True, is_sellable=True,
    )
    proj = build_product_detail(sku="ONLY-SIZE", channel_ref="web")
    assert proj is not None
    assert proj.nutrition is None
