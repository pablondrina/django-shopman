"""Tests for NutritionFacts dataclass + Product.clean() invariants."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from shopman.offerman.models import Product
from shopman.offerman.nutrition import (
    DRV_2000_KCAL,
    NUTRIENT_FIELDS,
    NUTRIENT_LABELS_PT,
    NutritionFacts,
)

pytestmark = pytest.mark.django_db


class TestNutritionFactsDataclass:
    def test_empty_from_dict_returns_none(self):
        assert NutritionFacts.from_dict(None) is None
        assert NutritionFacts.from_dict({}) is None

    def test_round_trip(self):
        facts = NutritionFacts(
            serving_size_g=50,
            servings_per_container=1,
            energy_kcal=180.0,
            carbohydrates_g=30.0,
            sugars_g=2.0,
            proteins_g=6.0,
            total_fat_g=4.5,
            saturated_fat_g=0.9,
            trans_fat_g=0.0,
            fiber_g=1.8,
            sodium_mg=340.0,
        )
        rehydrated = NutritionFacts.from_dict(facts.to_dict())
        assert rehydrated == facts

    def test_auto_filled_flag_preserved(self):
        facts = NutritionFacts.from_dict({"serving_size_g": 50, "auto_filled": True})
        assert facts.auto_filled is True

    def test_has_any_nutrient(self):
        empty = NutritionFacts(serving_size_g=50)
        assert not empty.has_any_nutrient
        with_energy = NutritionFacts(serving_size_g=50, energy_kcal=180.0)
        assert with_energy.has_any_nutrient

    def test_percent_daily_value_energy(self):
        facts = NutritionFacts(serving_size_g=50, energy_kcal=200.0)
        # 200 / 2000 * 100 = 10
        assert facts.percent_daily_value("energy_kcal") == 10

    def test_percent_daily_value_sodium(self):
        facts = NutritionFacts(serving_size_g=50, sodium_mg=480.0)
        # 480 / 2400 * 100 = 20
        assert facts.percent_daily_value("sodium_mg") == 20

    def test_percent_daily_value_none_for_sugars(self):
        """ANVISA does not define a DRV for sugars; helper returns None."""
        facts = NutritionFacts(serving_size_g=50, sugars_g=10.0)
        assert facts.percent_daily_value("sugars_g") is None

    def test_percent_daily_value_none_for_zero(self):
        facts = NutritionFacts(serving_size_g=50, energy_kcal=0.0)
        assert facts.percent_daily_value("energy_kcal") is None

    def test_percent_daily_value_ignores_unknown(self):
        facts = NutritionFacts(serving_size_g=50)
        assert facts.percent_daily_value("bogus_field") is None

    def test_nutrient_labels_cover_all_fields(self):
        """Every dataclass nutrient has a pt-BR label."""
        for field in ("serving_size_g", "servings_per_container") + NUTRIENT_FIELDS:
            assert field in NUTRIENT_LABELS_PT

    def test_drv_constants_are_positive(self):
        for key, value in DRV_2000_KCAL.items():
            assert value > 0, f"DRV for {key} must be > 0"


class TestProductCleanNutrition:
    def _make(self, **overrides) -> Product:
        return Product(
            sku=overrides.pop("sku", "TST"),
            name=overrides.pop("name", "Test"),
            base_price_q=overrides.pop("base_price_q", 100),
            **overrides,
        )

    def test_empty_nutrition_facts_is_valid(self):
        p = self._make(nutrition_facts={})
        p.clean()

    def test_nutrient_without_serving_raises(self):
        p = self._make(nutrition_facts={"energy_kcal": 180.0})
        with pytest.raises(ValidationError) as exc:
            p.clean()
        assert "porção" in str(exc.value).lower() or "servi" in str(exc.value).lower()

    def test_valid_serving_and_nutrient(self):
        p = self._make(nutrition_facts={
            "serving_size_g": 50,
            "energy_kcal": 180.0,
        })
        p.clean()

    def test_negative_value_raises(self):
        p = self._make(nutrition_facts={
            "serving_size_g": 50,
            "proteins_g": -1.0,
        })
        with pytest.raises(ValidationError):
            p.clean()

    def test_trans_greater_than_total_raises(self):
        p = self._make(nutrition_facts={
            "serving_size_g": 50,
            "total_fat_g": 2.0,
            "trans_fat_g": 3.0,
        })
        with pytest.raises(ValidationError):
            p.clean()

    def test_saturated_greater_than_total_raises(self):
        p = self._make(nutrition_facts={
            "serving_size_g": 50,
            "total_fat_g": 2.0,
            "saturated_fat_g": 3.0,
        })
        with pytest.raises(ValidationError):
            p.clean()

    def test_sugars_greater_than_carbs_raises(self):
        p = self._make(nutrition_facts={
            "serving_size_g": 50,
            "carbohydrates_g": 10.0,
            "sugars_g": 20.0,
        })
        with pytest.raises(ValidationError):
            p.clean()

    def test_servings_per_container_must_be_positive(self):
        p = self._make(nutrition_facts={
            "serving_size_g": 50,
            "servings_per_container": 0,
            "energy_kcal": 180.0,
        })
        with pytest.raises(ValidationError):
            p.clean()

    def test_non_dict_nutrition_raises(self):
        p = self._make()
        p.nutrition_facts = "junk"  # type: ignore[assignment]
        with pytest.raises(ValidationError):
            p.clean()

    def test_product_saves_with_valid_nutrition(self):
        p = self._make(nutrition_facts={
            "serving_size_g": 50,
            "energy_kcal": 180.0,
            "carbohydrates_g": 30.0,
            "sugars_g": 2.0,
            "proteins_g": 6.0,
            "total_fat_g": 4.5,
            "saturated_fat_g": 0.9,
            "trans_fat_g": 0.0,
            "fiber_g": 1.8,
            "sodium_mg": 340.0,
        })
        p.full_clean()
        p.save()
        p.refresh_from_db()
        assert p.nutrition_facts["energy_kcal"] == 180.0

    def test_product_ingredients_text_saves(self):
        p = self._make(ingredients_text="Farinha, água, sal.")
        p.save()
        p.refresh_from_db()
        assert p.ingredients_text == "Farinha, água, sal."
