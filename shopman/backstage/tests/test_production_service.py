"""Production command service facade tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from shopman.backstage.models import OperatorAlert
from shopman.backstage.services import production
from shopman.backstage.services.production import MissingMaterial, ProductionStockShortError
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.stockman.models import Batch


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        ref="svc-prod-v1",
        name="Serviço Produção",
        output_sku="SVC-PROD",
        batch_size=Decimal("10"),
    )


@pytest.mark.django_db
def test_apply_planned_start_finish_and_void(recipe):
    output_sku, wo_ref, qty, result = production.apply_planned(
        recipe_id=recipe.pk,
        quantity="10",
        target_date_value=date.today().isoformat(),
        actor="production:op",
    )
    work_order = WorkOrder.objects.get(ref=wo_ref)

    assert output_sku == recipe.output_sku
    assert qty == Decimal("10")
    assert result == "created"

    started_ref, started_qty = production.apply_start(
        work_order_id=work_order.pk,
        quantity="9",
        actor="production:op",
    )
    assert started_ref == wo_ref
    assert started_qty == Decimal("9")

    finished_ref, finished_qty = production.apply_finish(
        work_order_id=work_order.pk,
        quantity="8",
        actor="production:op",
    )
    assert finished_ref == wo_ref
    assert finished_qty == Decimal("8")

    planned = craft.plan(recipe, 5, date=date.today())
    assert production.apply_void(planned.pk, actor="production:op") == planned.ref


@pytest.mark.django_db
def test_apply_quick_finish_creates_finished_work_order(recipe):
    output_sku, wo_ref, qty = production.apply_quick_finish(
        recipe_id=recipe.pk,
        quantity="3",
        position_id="",
        actor="production:op",
    )

    work_order = WorkOrder.objects.get(ref=wo_ref)
    assert output_sku == recipe.output_sku
    assert qty == Decimal("3")
    assert work_order.status == WorkOrder.Status.FINISHED


def test_apply_finish_creates_stock_short_alert_before_reraising(monkeypatch):
    calls = []
    work_order = SimpleNamespace(pk=123, ref="WO-STOCK", output_sku="SKU-STOCK")

    def fail(*args, **kwargs):
        raise RuntimeError("estoque insuficiente")

    monkeypatch.setattr(production, "_get_work_order", lambda work_order_id: work_order)
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    monkeypatch.setattr(production.production_core, "finish_work_order", fail)
    monkeypatch.setattr(
        production,
        "_create_stock_short_alert",
        lambda **kwargs: calls.append(kwargs),
    )

    with pytest.raises(RuntimeError):
        production.apply_finish(work_order_id=123, quantity="1", actor="production:op")

    assert calls == [{"work_order_id": 123, "error": "estoque insuficiente"}]


def test_apply_finish_does_not_alert_for_non_stock_errors(monkeypatch):
    calls = []
    work_order = SimpleNamespace(pk=123, ref="WO-ERR", output_sku="SKU-ERR")

    def fail(*args, **kwargs):
        raise RuntimeError("erro genérico")

    monkeypatch.setattr(production, "_get_work_order", lambda work_order_id: work_order)
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    monkeypatch.setattr(production.production_core, "finish_work_order", fail)
    monkeypatch.setattr(
        production,
        "_create_stock_short_alert",
        lambda **kwargs: calls.append(kwargs),
    )

    with pytest.raises(RuntimeError):
        production.apply_finish(work_order_id=123, quantity="1", actor="production:op")

    assert calls == []


@pytest.mark.django_db
def test_apply_finish_blocks_when_materials_are_missing(recipe, monkeypatch):
    work_order = craft.plan(recipe, 10, date=date.today())
    missing = [MissingMaterial(sku="FARINHA", needed=Decimal("5"), available=Decimal("2"))]
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: missing)

    with pytest.raises(ProductionStockShortError) as exc:
        production.apply_finish(work_order_id=work_order.pk, quantity="10", actor="production:op")

    assert exc.value.missing == missing
    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.PLANNED


@pytest.mark.django_db
def test_apply_finish_force_creates_stock_short_alert(recipe, monkeypatch):
    work_order = craft.plan(recipe, 10, date=date.today())
    missing = [MissingMaterial(sku="FARINHA", needed=Decimal("5"), available=Decimal("2"))]
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: missing)

    production.apply_finish(
        work_order_id=work_order.pk,
        quantity="9",
        actor="production:op",
        force=True,
    )

    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.FINISHED
    assert OperatorAlert.objects.filter(type="production_stock_short", order_ref=work_order.ref).exists()


@pytest.mark.django_db
def test_apply_finish_records_batch_traceability(monkeypatch):
    recipe = Recipe.objects.create(
        ref="svc-batch-v1",
        name="Serviço Lote",
        output_sku="SVC-BATCH",
        batch_size=Decimal("10"),
        meta={"requires_batch_tracking": True, "shelf_life_days": 2},
    )
    work_order = craft.plan(recipe, 10, date=date.today())
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])

    production.apply_finish(work_order_id=work_order.pk, quantity="8", actor="production:op")

    work_order.refresh_from_db()
    assert work_order.meta["batch_ref"].startswith("SVC-BATCH-")
    assert work_order.meta["batch_quantity"] == "8"
    assert work_order.meta["expiry_date"] == (date.today() + production.timedelta(days=2)).isoformat()
    assert Batch.objects.filter(ref=work_order.meta["batch_ref"], sku="SVC-BATCH").exists()
