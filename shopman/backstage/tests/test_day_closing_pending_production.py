"""Fechamento do dia acusa produção aberta (WP-PE0).

O fechamento não bloqueia por WO aberta — acusa cedo e inline, com link para
resolver, e registra o pendente no snapshot para auditoria.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe

from shopman.backstage.models import DayClosing
from shopman.backstage.projections.closing import build_day_closing
from shopman.backstage.services.closing import perform_day_closing

pytestmark = pytest.mark.django_db


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        ref="croissant",
        name="Croissant",
        output_sku="CROISSANT",
        batch_size=1,
    )


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="closer", password="x")


class TestPendingProductionProjection:
    def test_open_work_orders_appear(self, recipe):
        planned = craft.plan(recipe, 10, date=date.today())
        started = craft.plan(recipe, 5, date=date.today())
        craft.start(started, quantity=5)

        closing = build_day_closing()
        assert closing.has_pending_production
        by_ref = {row.ref: row for row in closing.pending_production}
        assert by_ref[planned.ref].status == "planned"
        assert by_ref[planned.ref].status_label == "Planejada"
        assert not by_ref[planned.ref].is_overdue
        assert by_ref[started.ref].status == "started"
        assert by_ref[started.ref].status_label == "Em produção"

    def test_overdue_planned_is_flagged(self, recipe):
        craft.plan(recipe, 10, date=date.today() - timedelta(days=1))
        closing = build_day_closing()
        assert closing.pending_production[0].is_overdue

    def test_finished_and_voided_are_excluded(self, recipe):
        done = craft.plan(recipe, 10, date=date.today())
        craft.finish(order=done, finished=10)
        voided = craft.plan(recipe, 4, date=date.today())
        craft.void(order=voided, reason="teste")

        closing = build_day_closing()
        assert not closing.has_pending_production
        assert closing.pending_production == ()

    def test_future_planned_is_not_pending(self, recipe):
        craft.plan(recipe, 10, date=date.today() + timedelta(days=1))
        closing = build_day_closing()
        assert not closing.has_pending_production


class TestPendingProductionPage:
    def test_closing_page_shows_pending_block(self, recipe, client):
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType

        from shopman.shop.models import Shop

        Shop.objects.get_or_create(name="Test Shop")
        user = get_user_model().objects.create_user(
            username="closing-op", password="x", is_staff=True
        )
        ct = ContentType.objects.get_for_model(DayClosing)
        user.user_permissions.add(
            Permission.objects.get(content_type=ct, codename="perform_closing")
        )
        client.force_login(user)

        wo = craft.plan(recipe, 10, date=date.today() - timedelta(days=1))
        resp = client.get("/admin/operacao/fechamento/")

        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Producao pendente" in content
        assert wo.ref in content
        assert "(atrasada)" in content

    def test_closing_page_hides_block_without_pending(self, client):
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType

        from shopman.shop.models import Shop

        Shop.objects.get_or_create(name="Test Shop")
        user = get_user_model().objects.create_user(
            username="closing-op2", password="x", is_staff=True
        )
        ct = ContentType.objects.get_for_model(DayClosing)
        user.user_permissions.add(
            Permission.objects.get(content_type=ct, codename="perform_closing")
        )
        client.force_login(user)

        resp = client.get("/admin/operacao/fechamento/")
        assert resp.status_code == 200
        assert "Producao pendente" not in resp.content.decode()


class TestPendingProductionSnapshot:
    def test_closing_snapshot_records_pending(self, recipe, user):
        wo = craft.plan(recipe, 10, date=date.today())
        perform_day_closing(user=user, items=[], quantities_by_sku={})

        closing = DayClosing.objects.get()
        pending = closing.data["pending_production"]
        assert len(pending) == 1
        assert pending[0]["ref"] == wo.ref
        assert pending[0]["status"] == "planned"
        assert pending[0]["output_sku"] == "CROISSANT"

    def test_snapshot_empty_when_no_pending(self, user):
        perform_day_closing(user=user, items=[], quantities_by_sku={})
        closing = DayClosing.objects.get()
        assert closing.data["pending_production"] == []
