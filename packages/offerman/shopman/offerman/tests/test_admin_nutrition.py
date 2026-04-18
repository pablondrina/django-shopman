"""Admin form test for Product nutrition fields."""

from __future__ import annotations

import pytest
from shopman.offerman.contrib.admin_unfold.nutrition_form import ProductAdminForm
from shopman.offerman.models import Product

pytestmark = pytest.mark.django_db


def _base_data(**overrides) -> dict:
    data = {
        "sku": "TST",
        "name": "Test",
        "unit": "un",
        "short_description": "",
        "long_description": "",
        "keywords": "",
        "base_price_q": "100",
        "availability_policy": "planned_ok",
        "ingredients_text": "",
        "is_published": "on",
        "is_sellable": "on",
        "nutrition_facts": "{}",
        "metadata": "{}",
    }
    data.update(overrides)
    return data


def test_form_renders_nutrition_fields():
    form = ProductAdminForm()
    # Virtual fields injected
    for name in (
        "serving_size_g",
        "energy_kcal",
        "carbohydrates_g",
        "sugars_g",
        "sodium_mg",
    ):
        assert name in form.fields


def test_form_populates_initial_from_instance():
    product = Product.objects.create(
        sku="INIT",
        name="Init",
        base_price_q=100,
        nutrition_facts={
            "serving_size_g": 50,
            "energy_kcal": 180.0,
            "proteins_g": 6.0,
            "auto_filled": False,
        },
    )
    form = ProductAdminForm(instance=product)
    assert form.fields["serving_size_g"].initial == 50
    assert form.fields["energy_kcal"].initial == 180.0
    assert form.fields["proteins_g"].initial == 6.0


def test_form_serializes_to_json_on_save():
    product = Product.objects.create(
        sku="SAVE",
        name="Save",
        base_price_q=100,
    )
    data = _base_data(
        sku="SAVE",
        name="Save",
        serving_size_g="50",
        energy_kcal="180",
        proteins_g="6",
    )
    form = ProductAdminForm(data=data, instance=product)
    assert form.is_valid(), form.errors
    saved = form.save()
    saved.refresh_from_db()
    assert saved.nutrition_facts["serving_size_g"] == 50
    assert saved.nutrition_facts["energy_kcal"] == 180.0
    assert saved.nutrition_facts["auto_filled"] is False


def test_form_rejects_invalid_invariant():
    """trans > total must be blocked by Product.clean() via form.full_clean()."""
    product = Product.objects.create(
        sku="BAD",
        name="Bad",
        base_price_q=100,
    )
    data = _base_data(
        sku="BAD",
        name="Bad",
        serving_size_g="50",
        total_fat_g="2",
        trans_fat_g="3",
    )
    form = ProductAdminForm(data=data, instance=product)
    assert not form.is_valid()
