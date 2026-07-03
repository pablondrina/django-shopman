"""Pesagem cega (QA Pablo 2026-07-03) — código por (preparo, dia).

Formato "B7" (1 letra + 1 número, sem 0/1/O/I — ultra legível): sorteio com
retry só na colisão, alocação persistida em BlindPrepCode (estável o dia
todo). Regras anticonfusão: NO DIA, letra e número nunca repetem entre
códigos (Z7 veta Z9 e S7 — teto 8 preparos/dia); na JANELA de expediente
(dia útil anterior · dia · próximo dia útil; domingo/feriado pulam) o código
completo não repete. Mapa código↔preparo = gestor.
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

    def test_no_letter_nor_digit_repeats_within_day(self):
        """Z7 veta Z9 (letra) e S7 (número): confusão zero entre códigos do dia."""
        today = date.today()
        codes = [blind_prep_code(f"preparo-{i}", today) for i in range(8)]
        letters = [code[0] for code in codes]
        digits = [code[1] for code in codes]
        assert len(set(letters)) == 8
        assert len(set(digits)) == 8

    def test_ninth_prep_in_a_day_fails_explicitly(self):
        """8 dígitos válidos ⇒ teto de 8 preparos/dia — estouro acusa, não confunde."""
        today = date.today()
        for i in range(8):
            blind_prep_code(f"preparo-{i}", today)
        with pytest.raises(RuntimeError, match="8 preparos"):
            blind_prep_code("nono-preparo", today)

    def test_format_is_one_letter_one_digit_no_ambiguous_chars(self):
        """1 letra + 1 número, sem 0/1/O/I — ultra legível e memorizável."""
        today = date.today()
        for i in range(8):
            code = blind_prep_code(f"preparo-{i}", today)
            assert re.fullmatch(r"[A-HJ-NP-Z][2-9]", code), code

    def test_refs_differ_within_day(self):
        today = date.today()
        assert blind_prep_code("massa-brioche", today) != blind_prep_code("massa-campagne", today)

    def test_unique_across_adjacent_days_window(self):
        """Etiqueta de ontem na câmara nunca colide com a de hoje ou amanhã."""
        today = date.today()
        codes_today = {blind_prep_code(f"hoje-{i}", today) for i in range(8)}
        codes_tomorrow = {
            blind_prep_code(f"amanha-{i}", today + timedelta(days=1)) for i in range(8)
        }
        codes_yesterday = {
            blind_prep_code(f"ontem-{i}", today - timedelta(days=1)) for i in range(8)
        }
        assert not (codes_today & codes_tomorrow)
        assert not (codes_today & codes_yesterday)

    def test_window_skips_sunday(self):
        """Sábado e segunda são adjacentes (domingo sem expediente)."""
        from shopman.backstage.projections.production import _blind_window
        from shopman.shop.models import Shop

        Shop.objects.create(
            name="Nelson",
            opening_hours={
                day: {"open": "07:00", "close": "19:00"}
                for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
            },
        )
        # Uma segunda-feira qualquer: o dia útil anterior é o SÁBADO.
        monday = date(2026, 7, 6)
        assert monday.weekday() == 0
        window = _blind_window(monday)
        assert window == (date(2026, 7, 4), monday, date(2026, 7, 7))

        # E o próximo dia útil do sábado é a SEGUNDA.
        saturday = date(2026, 7, 4)
        assert _blind_window(saturday) == (date(2026, 7, 3), saturday, monday)

    def test_saturday_and_monday_never_share_codes(self):
        from shopman.shop.models import Shop

        Shop.objects.create(
            name="Nelson",
            opening_hours={
                day: {"open": "07:00", "close": "19:00"}
                for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
            },
        )
        saturday = date(2026, 7, 4)
        monday = date(2026, 7, 6)
        codes_sat = {blind_prep_code(f"sab-{i}", saturday) for i in range(8)}
        codes_mon = {blind_prep_code(f"seg-{i}", monday) for i in range(8)}
        assert not (codes_sat & codes_mon)

    def test_without_calendar_window_is_simple_yesterday_today_tomorrow(self):
        from shopman.backstage.projections.production import _blind_window

        today = date.today()
        assert _blind_window(today) == (
            today - timedelta(days=1),
            today,
            today + timedelta(days=1),
        )

    def test_full_window_still_allocates_every_day(self):
        """8+8+8 na janela: dias vizinhos lotados não travam o dia corrente."""
        today = date.today()
        all_codes = []
        for offset, prefix in ((-1, "ontem"), (0, "hoje"), (1, "amanha")):
            day = today + timedelta(days=offset)
            all_codes.extend(blind_prep_code(f"{prefix}-{i}", day) for i in range(8))
        assert len(set(all_codes)) == 24  # código completo único na janela


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
