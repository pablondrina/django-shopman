"""Mise en place — craft.needs() com projection e superfície (WP-PE3).

A lista de pesagem/separação do dia: insumos agregados das WOs abertas
(planned+started) da data, escalados pelo coeficiente, com quebra por receita
e saldo de estoque quando o ledger de insumos tem leitura (degrade gracioso).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIClient
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, RecipeItem

from shopman.backstage.models import DayClosing
from shopman.backstage.projections.production import build_production_mise_en_place

pytestmark = pytest.mark.django_db


@pytest.fixture
def pao(db):
    recipe = Recipe.objects.create(
        ref="pao-frances", name="Pão Francês", output_sku="PAO-FRANCES", batch_size=10
    )
    RecipeItem.objects.create(recipe=recipe, input_sku="FARINHA", quantity="5", unit="kg")
    RecipeItem.objects.create(recipe=recipe, input_sku="SAL", quantity="0.1", unit="kg")
    return recipe


@pytest.fixture
def brioche(db):
    recipe = Recipe.objects.create(
        ref="brioche", name="Brioche", output_sku="BRIOCHE", batch_size=10
    )
    RecipeItem.objects.create(recipe=recipe, input_sku="FARINHA", quantity="4", unit="kg")
    RecipeItem.objects.create(recipe=recipe, input_sku="OVOS", quantity="20", unit="un")
    return recipe


class TestMiseEnPlaceAggregation:
    def test_aggregates_across_recipes(self, pao, brioche):
        craft.plan(pao, 20, date=date.today())  # coef 2 → 10kg farinha, 0.2kg sal
        craft.plan(brioche, 10, date=date.today())  # coef 1 → 4kg farinha, 20 ovos

        projection = build_production_mise_en_place(selected_date=date.today())
        by_sku = {line.sku: line for line in projection.lines}

        assert projection.has_lines
        assert projection.work_order_count == 2
        assert by_sku["FARINHA"].quantity_display == "14 kg"
        assert by_sku["SAL"].quantity_display == "0,2 kg"
        assert by_sku["OVOS"].quantity_display == "20 un"

    def test_breakdown_per_recipe(self, pao, brioche):
        craft.plan(pao, 20, date=date.today())
        craft.plan(brioche, 10, date=date.today())

        projection = build_production_mise_en_place(selected_date=date.today())
        farinha = next(line for line in projection.lines if line.sku == "FARINHA")
        breakdown = {row.recipe_name: row.quantity_display for row in farinha.breakdown}
        assert breakdown == {"Pão Francês": "10 kg", "Brioche": "4 kg"}

    def test_started_wos_count_and_other_dates_do_not(self, pao):
        started = craft.plan(pao, 10, date=date.today())
        craft.start(started, quantity=10)
        craft.plan(pao, 30, date=date.today() + timedelta(days=1))  # amanhã, fora

        projection = build_production_mise_en_place(selected_date=date.today())
        farinha = next(line for line in projection.lines if line.sku == "FARINHA")
        assert farinha.quantity_display == "5 kg"

    def test_finished_and_voided_excluded(self, pao):
        done = craft.plan(pao, 10, date=date.today())
        craft.finish(order=done, finished=10)
        voided = craft.plan(pao, 10, date=date.today())
        craft.void(order=voided, reason="teste")

        projection = build_production_mise_en_place(selected_date=date.today())
        assert not projection.has_lines
        assert projection.lines == ()

    def test_empty_day(self):
        projection = build_production_mise_en_place(selected_date=date.today())
        assert not projection.has_lines
        assert projection.work_order_count == 0


class TestMiseEnPlaceExpand:
    def test_expand_explodes_subrecipe_into_raw_materials(self, pao):
        # MASSA-BASE é sub-receita: insumo do croissant e output da recipe massa.
        massa = Recipe.objects.create(
            ref="massa-base", name="Massa Base", output_sku="MASSA-BASE", batch_size=1
        )
        RecipeItem.objects.create(recipe=massa, input_sku="FARINHA", quantity="0.5", unit="kg")
        croissant = Recipe.objects.create(
            ref="croissant", name="Croissant", output_sku="CROISSANT", batch_size=10
        )
        RecipeItem.objects.create(
            recipe=croissant, input_sku="MASSA-BASE", quantity="2", unit="kg"
        )
        craft.plan(croissant, 10, date=date.today())

        immediate = build_production_mise_en_place(selected_date=date.today())
        assert [line.sku for line in immediate.lines] == ["MASSA-BASE"]
        assert immediate.lines[0].is_subrecipe

        expanded = build_production_mise_en_place(selected_date=date.today(), expand=True)
        assert [line.sku for line in expanded.lines] == ["FARINHA"]
        assert expanded.lines[0].quantity_display == "1 kg"  # 2kg massa × 0.5kg/1kg
        assert expanded.expanded


class TestMiseEnPlaceAvailability:
    def test_without_stock_readings_column_hides(self, pao):
        craft.plan(pao, 10, date=date.today())
        projection = build_production_mise_en_place(selected_date=date.today())
        assert not projection.has_stock_readings

    def test_subrecipes_never_flag_shortage(self, pao):
        """Pré-preparo é produzido na hora — saldo/falta é só para matéria-prima."""
        from shopman.stockman import Position
        from shopman.stockman.services.movements import StockMovements

        massa = Recipe.objects.create(
            ref="massa-base", name="Massa Base", output_sku="MASSA-BASE", batch_size=1
        )
        RecipeItem.objects.create(recipe=massa, input_sku="FARINHA", quantity="0.5", unit="kg")
        croissant = Recipe.objects.create(
            ref="croissant", name="Croissant", output_sku="CROISSANT", batch_size=10
        )
        RecipeItem.objects.create(recipe=croissant, input_sku="MASSA-BASE", quantity="2", unit="kg")
        despensa = Position.objects.create(ref="despensa", name="Despensa", is_saleable=True)
        StockMovements.receive(quantity=Decimal("1"), sku="FARINHA", position=despensa, reason="seed")

        craft.plan(croissant, 10, date=date.today())
        projection = build_production_mise_en_place(selected_date=date.today())

        massa_line = next(line for line in projection.lines if line.sku == "MASSA-BASE")
        assert massa_line.is_subrecipe
        assert massa_line.available_display == ""
        assert not massa_line.is_short

    def test_with_stock_reading_annotates_and_flags_shortage(self, pao):
        from shopman.stockman import Position
        from shopman.stockman.services.movements import StockMovements

        despensa = Position.objects.create(ref="despensa", name="Despensa", is_saleable=True)
        StockMovements.receive(quantity=Decimal("3"), sku="FARINHA", position=despensa, reason="seed")

        craft.plan(pao, 20, date=date.today())  # precisa 10kg, tem 3kg
        projection = build_production_mise_en_place(selected_date=date.today())

        assert projection.has_stock_readings
        farinha = next(line for line in projection.lines if line.sku == "FARINHA")
        assert farinha.available_display == "3 kg"
        assert farinha.is_short
        sal = next(line for line in projection.lines if line.sku == "SAL")
        assert not sal.available_display or sal.available_display == "0 kg"


class TestMiseEnPlaceAPI:
    def test_endpoint_returns_projection(self, pao):
        craft.plan(pao, 10, date=date.today())

        user = get_user_model().objects.create_user(username="floor", password="x", is_staff=True)
        ct = ContentType.objects.get_for_model(DayClosing)
        user.user_permissions.add(
            Permission.objects.get(content_type=ct, codename="operate_production")
        )
        client = APIClient()
        client.force_authenticate(user)

        resp = client.get("/api/v1/backstage/production/mise-en-place/")
        assert resp.status_code == 200
        payload = resp.json()["mise_en_place"]
        assert payload["has_lines"]
        assert payload["lines"][0]["sku"] == "FARINHA"

    def test_endpoint_requires_permission(self):
        user = get_user_model().objects.create_user(username="nobody", password="x")
        client = APIClient()
        client.force_authenticate(user)
        resp = client.get("/api/v1/backstage/production/mise-en-place/")
        assert resp.status_code == 403
