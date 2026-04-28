"""Production dashboard, KDS and alert surface tests."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from shopman.backstage.models import OperatorAlert
from shopman.backstage.projections.production import (
    build_production_dashboard,
    build_production_kds,
    build_work_order_card,
    resolve_production_access,
)
from shopman.backstage.services.production import MissingMaterial, ProductionStockShortError
from shopman.backstage.views.production import production_dashboard_view, production_kds_view
from shopman.backstage.views.production import bulk_create_work_orders
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.shop.models import Shop
from shopman.shop.handlers.production_alerts import (
    check_late_started_orders,
    create_stock_short_alert,
    maybe_create_low_yield_alert,
)


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser("admin", "admin@test.com", "pass")


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        ref="prod-op-v1",
        name="Produto Operacional",
        output_sku="PROD-OP",
        batch_size=Decimal("10"),
        steps=["Mistura", "Forno"],
        meta={"max_started_minutes": 30, "capacity_per_day": 100},
    )


@pytest.mark.django_db
def test_production_dashboard_projection_summarizes_day_and_late_orders(recipe):
    planned = craft.plan(recipe, 20, date=date.today(), position_ref="forno")
    started = craft.plan(recipe, 30, date=date.today(), position_ref="forno")
    craft.start(started, quantity=30, position_ref="forno", expected_rev=0)
    WorkOrder.objects.filter(pk=started.pk).update(started_at=timezone.now() - timedelta(minutes=45))
    finished = craft.plan(recipe, 40, date=date.today(), position_ref="forno")
    craft.finish(finished, finished=36, actor="test")

    dashboard = build_production_dashboard(selected_date=date.today(), position_ref="forno")

    assert dashboard.planned_orders == 1
    assert dashboard.started_orders == 1
    assert dashboard.finished_orders == 1
    assert dashboard.planned_qty == "90"
    assert dashboard.started_qty == "70"
    assert dashboard.finished_qty == "36"
    assert dashboard.average_yield_rate == "90%"
    assert dashboard.capacity_percent == 90
    assert dashboard.late_orders[0].ref == started.ref


@pytest.mark.django_db
def test_production_kds_projection_returns_started_cards_only(recipe, superuser):
    planned = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    started = craft.plan(recipe, 12, date=date.today(), position_ref="forno", operator_ref="user:ana")
    craft.start(started, quantity=11, position_ref="forno", expected_rev=0)
    craft.finish(craft.plan(recipe, 8, date=date.today(), position_ref="forno"), finished=7, actor="test")

    access = resolve_production_access(superuser)
    kds = build_production_kds(selected_date=date.today(), position_ref="forno", access=access)

    assert kds.total_count == 1
    assert kds.cards[0].ref == started.ref
    assert kds.cards[0].started_qty == "11"
    assert kds.cards[0].current_step == "Mistura"
    assert kds.cards[0].can_finish is True
    assert planned.ref not in [card.ref for card in kds.cards]


@pytest.mark.django_db
def test_work_order_card_preserves_decimal_quantities(recipe):
    work_order = craft.plan(recipe, Decimal("1.5"), date=date.today(), position_ref="forno")
    craft.start(work_order, quantity=Decimal("1.25"), position_ref="forno", expected_rev=0)
    craft.finish(work_order, finished=Decimal("1.125"), actor="test")

    card = build_work_order_card(work_order.ref)

    assert card.planned_qty == "1.5"
    assert card.started_qty == "1.25"
    assert card.finished_qty == "1.125"
    assert card.loss == "0.125"


@pytest.mark.django_db
def test_production_dashboard_and_kds_views_render(recipe, rf, superuser):
    started = craft.plan(recipe, 12, date=date.today(), position_ref="forno")
    craft.start(started, quantity=12, position_ref="forno", expected_rev=0)

    dashboard_request = rf.get("/gestor/producao/dashboard/")
    dashboard_request.user = superuser
    dashboard_response = production_dashboard_view(dashboard_request)
    assert dashboard_response.status_code == 200
    assert dashboard_response.context_data["dashboard"].started_orders == 1

    kds_request = rf.get("/gestor/producao/kds/")
    kds_request.user = superuser
    kds_response = production_kds_view(kds_request)
    assert kds_response.status_code == 200
    assert kds_response.context_data["kds"].total_count == 1


@pytest.mark.django_db
def test_low_yield_alert_created_once(recipe):
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    craft.start(work_order, quantity=10, position_ref="forno", expected_rev=0)
    craft.finish(work_order, finished=7, actor="test")

    OperatorAlert.objects.all().delete()
    assert maybe_create_low_yield_alert(work_order) is True
    assert maybe_create_low_yield_alert(work_order) is False
    alert = OperatorAlert.objects.get(type="production_low_yield")
    assert alert.order_ref == work_order.ref
    assert "yield de 70%" in alert.message


@pytest.mark.django_db
def test_late_started_alert_created_once(recipe):
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    craft.start(work_order, quantity=10, position_ref="forno", expected_rev=0)
    WorkOrder.objects.filter(pk=work_order.pk).update(started_at=timezone.now() - timedelta(minutes=45))

    assert check_late_started_orders(selected_date=date.today()) == 1
    assert check_late_started_orders(selected_date=date.today()) == 0
    alert = OperatorAlert.objects.get(type="production_late")
    assert alert.order_ref == work_order.ref


@pytest.mark.django_db
def test_stock_short_alert_created_once(recipe):
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")

    create_stock_short_alert(
        work_order_ref=work_order.ref,
        output_sku=work_order.output_sku,
        error="estoque insuficiente",
    )
    create_stock_short_alert(
        work_order_ref=work_order.ref,
        output_sku=work_order.output_sku,
        error="estoque insuficiente",
    )

    assert OperatorAlert.objects.filter(type="production_stock_short").count() == 1


@pytest.mark.django_db
def test_bulk_create_work_orders_accepts_htmx_form(recipe, rf, superuser):
    request = rf.post(
        "/gestor/producao/criar/",
        {
            "date": date.today().isoformat(),
            "recipe_ref": [recipe.ref],
            "quantity": ["12"],
        },
    )
    request.user = superuser
    request.session = {}

    response = bulk_create_work_orders(request)

    assert response.status_code == 200
    assert WorkOrder.objects.filter(recipe=recipe, quantity=Decimal("12")).exists()
    assert recipe.output_sku.encode() in response.content


@pytest.mark.django_db
def test_finish_action_returns_material_shortage_partial(client, recipe, superuser, monkeypatch):
    Shop.objects.create(name="Loja Produção")
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.force_login(superuser)

    def block_finish(**kwargs):
        raise ProductionStockShortError(
            work_order_ref=work_order.ref,
            missing=[MissingMaterial(sku="FARINHA", needed=Decimal("5"), available=Decimal("2"))],
        )

    monkeypatch.setattr(
        "shopman.backstage.views.production.production_service.apply_finish",
        block_finish,
    )

    response = client.post(
        reverse("backstage:production"),
        {"action": "finish", "wo_id": work_order.pk, "quantity": "10"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"Insumos insuficientes" in response.content
    assert b"FARINHA" in response.content
    assert b'name="force" value="1"' in response.content
