"""Pesagem cega (QA Pablo 2026-07-03) — código por (preparo, dia).

Cada preparo ganha um código diário aleatório-parecido (HMAC do SECRET_KEY,
sem tabela): estável o dia todo (reimpressão bate), muda a cada dia, e não
revela a receita. As etiquetas circulam só com o código; o mapa código↔preparo
é visão de gestor.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal

import pytest
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, RecipeItem

from shopman.backstage.projections.production import (
    blind_prep_code,
    build_production_weighing,
)

pytestmark = pytest.mark.django_db


class TestBlindPrepCode:
    def test_deterministic_within_day(self):
        today = date.today()
        assert blind_prep_code("massa-brioche", today) == blind_prep_code("massa-brioche", today)

    def test_changes_across_days_and_refs(self):
        today = date.today()
        assert blind_prep_code("massa-brioche", today) != blind_prep_code(
            "massa-brioche", today + timedelta(days=1)
        )
        assert blind_prep_code("massa-brioche", today) != blind_prep_code("massa-campagne", today)

    def test_format_is_opaque(self):
        code = blind_prep_code("massa-brioche", date.today())
        assert re.fullmatch(r"P-[A-Z2-7]{6}", code)
        assert "brioche" not in code.lower()


class TestWeighingAPI:
    def test_endpoint_returns_tickets_with_blind_code(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        from rest_framework.test import APIClient

        from shopman.backstage.models import DayClosing

        massa = Recipe.objects.create(
            ref="massa-pao", name="Massa Pão", output_sku="MASSA-PAO", batch_size=Decimal("1")
        )
        RecipeItem.objects.create(recipe=massa, input_sku="FARINHA", quantity="0.6", unit="kg")
        pao = Recipe.objects.create(
            ref="pao", name="Pão", output_sku="PAO", batch_size=Decimal("10")
        )
        RecipeItem.objects.create(recipe=pao, input_sku="MASSA-PAO", quantity="7", unit="kg")
        craft.plan(pao, Decimal("10"), date=date.today())

        user = get_user_model().objects.create_user(username="scale", password="x", is_staff=True)
        ct = ContentType.objects.get_for_model(DayClosing)
        user.user_permissions.add(
            Permission.objects.get(content_type=ct, codename="operate_production")
        )
        client = APIClient()
        client.force_authenticate(user)

        resp = client.get("/api/v1/backstage/production/weighing/")
        assert resp.status_code == 200
        tickets = resp.json()["weighing"]["tickets"]
        ticket = next(t for t in tickets if t["recipe_ref"] == "massa-pao")
        assert ticket["blind_code"].startswith("P-")
        assert ticket["ingredients"][0]["sku"] == "FARINHA"
        assert ticket["ingredients"][0]["quantity_display"] == "4,2 kg"

    def test_endpoint_requires_permission(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient

        user = get_user_model().objects.create_user(username="nobody2", password="x")
        client = APIClient()
        client.force_authenticate(user)
        assert client.get("/api/v1/backstage/production/weighing/").status_code == 403


class TestAdminBlindMap:
    def test_gestor_sees_blind_map_on_weighing_page(self, client):
        from django.contrib.auth import get_user_model

        from shopman.shop.models import Shop

        Shop.objects.get_or_create(name="Test Shop")
        massa = Recipe.objects.create(
            ref="massa-map", name="Massa Map", output_sku="MASSA-MAP", batch_size=Decimal("1")
        )
        RecipeItem.objects.create(recipe=massa, input_sku="FARINHA", quantity="1", unit="kg")
        final = Recipe.objects.create(
            ref="final-map", name="Final Map", output_sku="FINAL-MAP", batch_size=Decimal("1")
        )
        RecipeItem.objects.create(recipe=final, input_sku="MASSA-MAP", quantity="1", unit="kg")
        craft.plan(final, Decimal("5"), date=date.today())

        gestor = get_user_model().objects.create_superuser("gestor-map", "g@x.com", "x")
        client.force_login(gestor)

        resp = client.get("/admin/operacao/producao/pesagem/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Mapa de codigos cegos" in content
        assert blind_prep_code("massa-map", date.today()) in content


class TestWeighingTicketsCarryBlindCode:
    def test_tickets_expose_blind_code(self):
        massa = Recipe.objects.create(
            ref="massa-croissant", name="Massa Croissant", output_sku="MASSA-CROISSANT",
            batch_size=Decimal("1"),
        )
        RecipeItem.objects.create(recipe=massa, input_sku="FARINHA", quantity="0.5", unit="kg")
        croissant = Recipe.objects.create(
            ref="croissant", name="Croissant", output_sku="CROISSANT", batch_size=Decimal("10")
        )
        RecipeItem.objects.create(
            recipe=croissant, input_sku="MASSA-CROISSANT", quantity="2", unit="kg"
        )
        craft.plan(croissant, Decimal("10"), date=date.today())

        weighing = build_production_weighing(selected_date=date.today())
        ticket = next(t for t in weighing.tickets if t.recipe_ref == "massa-croissant")
        assert ticket.blind_code == blind_prep_code("massa-croissant", date.today())
        assert ticket.ingredients[0].sku == "FARINHA"
