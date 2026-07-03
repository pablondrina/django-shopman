"""Recipe.meta["production_lifecycle"] estruturado no admin de receitas (WP-PE1).

O campo é provider-driven: o contrib Unfold do Craftsman só o renderiza porque
``CRAFTSMAN["PRODUCTION_LIFECYCLE_PROVIDER"]`` aponta para as variantes do
dispatch do orquestrador. Sem provider, o campo não existe (pacote standalone).
"""

from __future__ import annotations

import pytest
from django.contrib import admin
from shopman.craftsman.models import Recipe

pytestmark = pytest.mark.django_db


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        ref="baguete",
        name="Baguete",
        output_sku="BAGUETE",
        batch_size=1,
    )


def _form_class():
    return admin.site._registry[Recipe].form


def _form_data(recipe: Recipe, **overrides) -> dict:
    data = {
        "ref": recipe.ref,
        "name": recipe.name,
        "output_sku": recipe.output_sku,
        "batch_size": "1",
        "is_active": "on",
        "production_lifecycle": "standard",
    }
    data.update(overrides)
    return data


class TestRecipeLifecycleField:
    def test_choices_come_from_orchestrator_dispatch_table(self, recipe):
        form = _form_class()(instance=recipe)
        values = [value for value, _ in form.fields["production_lifecycle"].choices]
        assert values == ["standard", "forecast", "subcontract"]

    def test_standard_keeps_meta_clean(self, recipe):
        form = _form_class()(data=_form_data(recipe), instance=recipe)
        assert form.is_valid(), form.errors
        saved = form.save()
        assert "production_lifecycle" not in (saved.meta or {})

    def test_variant_is_persisted(self, recipe):
        form = _form_class()(
            data=_form_data(recipe, production_lifecycle="subcontract"), instance=recipe
        )
        assert form.is_valid(), form.errors
        saved = form.save()
        assert saved.meta["production_lifecycle"] == "subcontract"

    def test_unknown_variant_is_rejected(self, recipe):
        form = _form_class()(
            data=_form_data(recipe, production_lifecycle="bogus"), instance=recipe
        )
        assert not form.is_valid()
        assert "production_lifecycle" in form.errors

    def test_initial_reflects_existing_meta(self, recipe):
        recipe.meta = {"production_lifecycle": "forecast"}
        recipe.save(update_fields=["meta"])
        form = _form_class()(instance=recipe)
        assert form.fields["production_lifecycle"].initial == "forecast"

    def test_field_absent_without_provider(self, recipe, settings):
        craftsman_settings = dict(settings.CRAFTSMAN)
        craftsman_settings.pop("PRODUCTION_LIFECYCLE_PROVIDER", None)
        settings.CRAFTSMAN = craftsman_settings
        form = _form_class()(instance=recipe)
        assert "production_lifecycle" not in form.fields
