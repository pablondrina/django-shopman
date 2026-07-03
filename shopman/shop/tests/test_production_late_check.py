"""
production.late_check — heartbeat de alertas de produção (WP-PE0).

O heartbeat é uma Directive auto-reagendável: roda as varreduras (started além
da janela, planned esquecida) e reenfileira a si mesma no cadence configurado.
Arma-se sozinha em qualquer ``production_changed`` — nenhuma tela precisa estar
aberta para o operador ser avisado.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.utils import timezone
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
from shopman.orderman.models import Directive

from shopman.backstage.models import OperatorAlert
from shopman.shop.directives import PRODUCTION_LATE_CHECK
from shopman.shop.handlers.production_alerts import (
    ProductionLateCheckHandler,
    check_forgotten_planned_orders,
    ensure_late_check_scheduled,
)
from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        ref="pao-frances",
        name="Pão Francês",
        output_sku="PAO-FRANCES",
        batch_size=1,
        meta={"max_started_minutes": 60},
    )


def _live_directives():
    return Directive.objects.filter(
        topic=PRODUCTION_LATE_CHECK, status__in=("queued", "running")
    )


# ── ensure_late_check_scheduled ──


class TestEnsureScheduled:
    def test_creates_directive_when_none_live(self):
        assert ensure_late_check_scheduled() is True
        directive = _live_directives().get()
        assert directive.status == "queued"
        # available_at ≈ now + cadence default (15 min)
        delta = directive.available_at - timezone.now()
        assert timedelta(minutes=14) < delta <= timedelta(minutes=15)

    def test_noop_when_already_live(self):
        ensure_late_check_scheduled()
        assert ensure_late_check_scheduled() is False
        assert _live_directives().count() == 1

    def test_noop_when_cadence_disabled(self):
        Shop.objects.create(
            name="Nelson",
            defaults={"production": {"alerts": {"late_check_cadence_minutes": 0}}},
        )
        assert ensure_late_check_scheduled() is False
        assert not _live_directives().exists()

    def test_production_changed_arms_heartbeat(self, recipe):
        craft.plan(recipe, 5, date=date.today())
        assert _live_directives().count() == 1


# ── check_forgotten_planned_orders ──


class TestForgottenPlanned:
    def test_overdue_planned_creates_alert(self, recipe):
        wo = craft.plan(recipe, 10, date=date.today() - timedelta(days=2))
        created = check_forgotten_planned_orders()
        assert created == 1
        alert = OperatorAlert.objects.get(type="production_forgotten")
        assert wo.ref in alert.message
        assert alert.severity == "warning"

    def test_dedups_within_window(self, recipe):
        craft.plan(recipe, 10, date=date.today() - timedelta(days=1))
        assert check_forgotten_planned_orders() == 1
        assert check_forgotten_planned_orders() == 0
        assert OperatorAlert.objects.filter(type="production_forgotten").count() == 1

    def test_planned_for_today_is_not_forgotten(self, recipe):
        craft.plan(recipe, 10, date=date.today())
        assert check_forgotten_planned_orders() == 0

    def test_started_orders_are_not_forgotten(self, recipe):
        wo = craft.plan(recipe, 10, date=date.today() - timedelta(days=1))
        craft.start(wo, quantity=10)
        assert check_forgotten_planned_orders() == 0


# ── ProductionLateCheckHandler ──


def _make_directive(**overrides) -> Directive:
    fields = {"topic": PRODUCTION_LATE_CHECK, "status": "running", "payload": {}}
    fields.update(overrides)
    return Directive.objects.create(**fields)


class TestLateCheckHandler:
    def test_runs_sweeps_and_requeues_itself(self, recipe):
        # WO started além da janela (meta 60 min, started há 2h)
        wo = craft.plan(recipe, 10, date=date.today())
        craft.start(wo, quantity=10)
        type(wo).objects.filter(pk=wo.pk).update(
            started_at=timezone.now() - timedelta(hours=2)
        )
        # WO planned esquecida (ontem)
        craft.plan(recipe, 5, date=date.today() - timedelta(days=1))
        Directive.objects.all().delete()  # limpa heartbeats armados pelos plans

        directive = _make_directive(attempts=3)
        ProductionLateCheckHandler().handle(message=directive, ctx={})

        assert OperatorAlert.objects.filter(type="production_late").count() == 1
        assert OperatorAlert.objects.filter(type="production_forgotten").count() == 1

        directive.refresh_from_db()
        assert directive.status == "queued"
        assert directive.attempts == 0  # heartbeat perpétuo nunca esgota retries
        delta = directive.available_at - timezone.now()
        assert timedelta(minutes=14) < delta <= timedelta(minutes=15)

    def test_cadence_from_config(self, recipe):
        Shop.objects.create(
            name="Nelson",
            defaults={"production": {"alerts": {"late_check_cadence_minutes": 45}}},
        )
        directive = _make_directive()
        ProductionLateCheckHandler().handle(message=directive, ctx={})
        directive.refresh_from_db()
        delta = directive.available_at - timezone.now()
        assert timedelta(minutes=44) < delta <= timedelta(minutes=45)

    def test_disabled_cadence_completes_without_requeue(self):
        Shop.objects.create(
            name="Nelson",
            defaults={"production": {"alerts": {"late_check_cadence_minutes": 0}}},
        )
        directive = _make_directive()
        ProductionLateCheckHandler().handle(message=directive, ctx={})
        directive.refresh_from_db()
        # Handler não toca o status: worker marca done (heartbeat desarmado).
        assert directive.status == "running"

    def test_duplicate_collapses_keeping_oldest(self):
        oldest = _make_directive(status="queued")
        duplicate = _make_directive()
        ProductionLateCheckHandler().handle(message=duplicate, ctx={})
        duplicate.refresh_from_db()
        oldest.refresh_from_db()
        assert duplicate.status == "running"  # worker marca done; não reagenda
        assert oldest.status == "queued"  # o mais antigo segue vivo
