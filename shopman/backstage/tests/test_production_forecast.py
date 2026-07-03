"""O PAINEL — previsão da produção (build_production_forecast).

Escada de status estilo aeroporto, ETA pela mediana histórica e a coluna
LIVRE (prevista − comprometida) para a equipe de vendas.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.craftsman.models import Recipe, WorkOrder

from shopman.backstage.projections.production import build_production_forecast

pytestmark = pytest.mark.django_db


def _tz():
    return timezone.get_current_timezone()


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=_tz())


@pytest.fixture
def recipe():
    return Recipe.objects.create(
        ref="pao-teste",
        name="Pão Teste",
        output_sku="PAO-TESTE",
        batch_size=Decimal("10"),
        is_active=True,
        meta={"max_started_minutes": 120},
    )


def _history(recipe, target: date, days: int = 5, start_hour: int = 5, finish_hour: int = 8):
    """WOs concluídas nos dias anteriores — a malha histórica do painel."""
    for offset in range(1, days + 1):
        day = target - timedelta(days=offset)
        WorkOrder.objects.create(
            recipe=recipe,
            output_sku=recipe.output_sku,
            quantity=Decimal("10"),
            finished=Decimal("9"),
            status=WorkOrder.Status.FINISHED,
            target_date=day,
            started_at=_at(day, start_hour),
            finished_at=_at(day, finish_hour),
        )


def test_planned_row_gets_eta_from_historical_finish_time(recipe):
    target = timezone.localdate() + timedelta(days=1)  # amanhã: nunca "atrasado"
    _history(recipe, target, finish_hour=8)
    WorkOrder.objects.create(
        recipe=recipe,
        output_sku=recipe.output_sku,
        quantity=Decimal("12"),
        status=WorkOrder.Status.PLANNED,
        target_date=target,
    )
    forecast = build_production_forecast(target)
    assert len(forecast.rows) == 1
    row = forecast.rows[0]
    assert row.status == "scheduled"
    assert row.status_label == "Programado"
    assert row.eta_display == "08:00"
    assert row.eta_is_actual is False
    assert row.forecast_qty == "12"
    assert row.qty_firm is False
    assert row.history_days == 5


def test_started_row_eta_is_start_plus_median_duration(recipe):
    target = timezone.localdate() + timedelta(days=1)
    _history(recipe, target, start_hour=5, finish_hour=8)  # duração mediana: 3h
    WorkOrder.objects.create(
        recipe=recipe,
        output_sku=recipe.output_sku,
        quantity=Decimal("12"),
        status=WorkOrder.Status.STARTED,
        target_date=target,
        started_at=_at(target, 6, 30),
    )
    row = build_production_forecast(target).rows[0]
    assert row.status == "in_progress"
    assert row.eta_display == "09:30"
    assert row.qty_firm is True


def test_started_row_without_history_falls_back_to_recipe_sla(recipe):
    target = timezone.localdate() + timedelta(days=1)
    WorkOrder.objects.create(
        recipe=recipe,
        output_sku=recipe.output_sku,
        quantity=Decimal("12"),
        status=WorkOrder.Status.STARTED,
        target_date=target,
        started_at=_at(target, 6, 0),
    )
    row = build_production_forecast(target).rows[0]
    assert row.eta_display == "08:00"  # 06:00 + max_started_minutes (120)
    assert row.history_days == 0


def test_finished_row_is_arrived_with_real_time_and_qty(recipe):
    target = timezone.localdate()
    WorkOrder.objects.create(
        recipe=recipe,
        output_sku=recipe.output_sku,
        quantity=Decimal("12"),
        finished=Decimal("10"),
        status=WorkOrder.Status.FINISHED,
        target_date=target,
        started_at=_at(target, 5, 0),
        finished_at=_at(target, 7, 45),
    )
    row = build_production_forecast(target).rows[0]
    assert row.status == "arrived"
    assert row.status_label == "Na vitrine"
    assert row.eta_display == "07:45"
    assert row.eta_is_actual is True
    assert row.forecast_qty == "10"
    assert row.qty_firm is True


def test_planned_past_eta_today_is_delayed(recipe):
    target = timezone.localdate()
    _history(recipe, target, finish_hour=0)  # história diz que conclui 00:00 → já passou
    WorkOrder.objects.create(
        recipe=recipe,
        output_sku=recipe.output_sku,
        quantity=Decimal("12"),
        status=WorkOrder.Status.PLANNED,
        target_date=target,
    )
    row = build_production_forecast(target).rows[0]
    assert row.status == "delayed"
    assert row.status_label == "Atrasado"


def test_planned_without_history_has_no_eta(recipe):
    target = timezone.localdate() + timedelta(days=1)
    WorkOrder.objects.create(
        recipe=recipe,
        output_sku=recipe.output_sku,
        quantity=Decimal("12"),
        status=WorkOrder.Status.PLANNED,
        target_date=target,
    )
    row = build_production_forecast(target).rows[0]
    assert row.eta_display == "—"
    assert row.status == "scheduled"


def test_void_orders_stay_off_the_board(recipe):
    target = timezone.localdate() + timedelta(days=1)
    WorkOrder.objects.create(
        recipe=recipe,
        output_sku=recipe.output_sku,
        quantity=Decimal("12"),
        status=WorkOrder.Status.VOID,
        target_date=target,
    )
    assert build_production_forecast(target).rows == ()


def test_rows_sort_by_eta_no_eta_last(recipe):
    target = timezone.localdate() + timedelta(days=1)
    late = Recipe.objects.create(
        ref="tarde", name="Fornada da Tarde", output_sku="TARDE",
        batch_size=Decimal("5"), is_active=True,
    )
    _history(recipe, target, finish_hour=8)
    _history(late, target, start_hour=13, finish_hour=15)
    for r in (late, recipe):
        WorkOrder.objects.create(
            recipe=r, output_sku=r.output_sku, quantity=Decimal("5"),
            status=WorkOrder.Status.PLANNED, target_date=target,
        )
    no_eta = Recipe.objects.create(
        ref="sem-historia", name="Sem História", output_sku="NOVO",
        batch_size=Decimal("5"), is_active=True,
    )
    WorkOrder.objects.create(
        recipe=no_eta, output_sku="NOVO", quantity=Decimal("5"),
        status=WorkOrder.Status.PLANNED, target_date=target,
    )
    skus = [row.output_sku for row in build_production_forecast(target).rows]
    assert skus == ["PAO-TESTE", "TARDE", "NOVO"]
