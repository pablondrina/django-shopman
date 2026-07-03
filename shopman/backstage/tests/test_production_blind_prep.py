"""Pesagem cega (QA Pablo 2026-07-03) — código por (preparo, dia).

Formato "B7" (1 letra + 1 número, sem 0/1/O/I — ultra legível): num espaço de
192, unicidade vem por CONSTRAINT (alocação persistida em BlindPrepCode), com
ordem de candidatos semeada pelo SECRET_KEY. Estável o dia todo mesmo com
preparos entrando no meio da manhã; as etiquetas circulam só com o código e o
mapa código↔preparo é visão de gestor.
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
    def test_stable_within_day(self):
        today = date.today()
        assert blind_prep_code("massa-brioche", today) == blind_prep_code("massa-brioche", today)

    def test_stable_even_when_new_preps_join_midday(self):
        """Reimpressão às 10h bate com a etiqueta das 6h, sempre."""
        today = date.today()
        first = blind_prep_code("massa-brioche", today)
        blind_prep_code("massa-campagne", today)  # preparo novo no meio da manhã
        blind_prep_code("massa-folhada", today)
        assert blind_prep_code("massa-brioche", today) == first

    def test_unique_within_day(self):
        today = date.today()
        codes = [blind_prep_code(f"preparo-{i}", today) for i in range(40)]
        assert len(set(codes)) == 40

    def test_format_is_one_letter_one_digit_no_ambiguous_chars(self):
        """1 letra + 1 número, sem 0/1/O/I — ultra legível e memorizável."""
        today = date.today()
        for i in range(40):
            code = blind_prep_code(f"preparo-{i}", today)
            assert re.fullmatch(r"[A-HJ-NP-Z][2-9]", code), code

    def test_refs_differ_within_day(self):
        today = date.today()
        assert blind_prep_code("massa-brioche", today) != blind_prep_code("massa-campagne", today)

    def test_days_allocate_independently(self):
        today = date.today()
        tomorrow = today + timedelta(days=1)
        # Amanhã realoca do zero (códigos reciclam por dia) — só garante que a
        # alocação de amanhã também é válida e estável.
        code_tomorrow = blind_prep_code("massa-brioche", tomorrow)
        assert re.fullmatch(r"[A-HJ-NP-Z][2-9]", code_tomorrow)
        assert blind_prep_code("massa-brioche", tomorrow) == code_tomorrow

    def test_space_exhaustion_raises_clearly(self):
        today = date.today()
        for i in range(192):
            blind_prep_code(f"lotação-{i}", today)
        with pytest.raises(RuntimeError, match="esgotado"):
            blind_prep_code("um-a-mais", today)


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
        assert re.fullmatch(r"[A-HJ-NP-Z][2-9]", ticket["blind_code"])
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
