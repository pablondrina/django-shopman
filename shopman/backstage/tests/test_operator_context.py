"""Shared operator context tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User

from shopman.backstage.models import CashRegisterSession, OperatorAlert
from shopman.backstage.operator.context import build_operator_context
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
from shopman.orderman.models import Order
from shopman.shop.models import Shop
from shopman.stockman.models import Position


def _grant(user, app_label: str, codename: str) -> None:
    perm = Permission.objects.get(content_type__app_label=app_label, codename=codename)
    user.user_permissions.add(perm)


@pytest.mark.django_db
def test_operator_context_summarizes_alerts_shift_kpis_and_permissions(rf):
    user = User.objects.create_user("op", password="x", is_staff=True)
    _grant(user, "backstage", "operate_pos")
    _grant(user, "backstage", "operate_kds")
    _grant(user, "shop", "manage_orders")
    _grant(user, "shop", "view_production_started")

    CashRegisterSession.objects.create(operator=user, opening_amount_q=1000)
    OperatorAlert.objects.create(type="stock_low", severity="warning", message="Estoque baixo")
    OperatorAlert.objects.create(type="production_late", severity="critical", message="Produção atrasada")
    Position.objects.create(ref="balcao", name="Balcão", is_default=True)
    Order.objects.create(ref="OP-1", channel_ref="pdv", total_q=2500, status=Order.Status.CONFIRMED)

    recipe = Recipe.objects.create(
        ref="ctx-prod-v1",
        name="Contexto Produção",
        output_sku="CTX-PROD",
        batch_size=Decimal("10"),
    )
    craft.plan(recipe, 10, date=date.today(), position_ref="producao")
    started = craft.plan(recipe, 8, date=date.today(), position_ref="producao")
    craft.start(started, quantity=8, position_ref="producao", expected_rev=0)

    request = rf.get("/admin/operacao/pedidos/")
    request.user = user
    context = build_operator_context(request)

    assert context.is_active is True
    assert context.shift_state == "open"
    assert context.active_alerts_count == 2
    assert context.critical_alerts_count == 1
    assert context.kpis_today.orders_count == 1
    assert context.kpis_today.revenue_q == 2500
    assert context.kpis_today.production_planned_orders == 1
    assert context.kpis_today.production_started_orders == 1
    assert context.position_default_ref == "balcao"
    assert context.permissions.can_operate_pos is True
    assert context.permissions.can_operate_kds is True
    assert context.permissions.can_manage_orders is True
    assert context.permissions.can_access_production is True
    assert context.event_scope == "main"


@pytest.mark.django_db
def test_operator_context_exposes_shop_scoped_event_channel(rf):
    user = User.objects.create_user("scoped-op", password="x", is_staff=True)
    shop = Shop.objects.create(name="Loja SSE")

    request = rf.get("/admin/operacao/pedidos/")
    request.user = user
    context = build_operator_context(request)

    assert context.event_scope == f"shop-{shop.pk}"


@pytest.mark.django_db
def test_alerts_badge_partial_uses_operator_context(client):
    user = User.objects.create_user("badge", password="x", is_staff=True)
    Shop.objects.create(name="Loja Teste")
    OperatorAlert.objects.create(type="production_late", severity="critical", message="Produção atrasada")

    client.force_login(user)
    response = client.get("/gestor/alertas/badge/")

    assert response.status_code == 200
    assert b"notification_important" in response.content
    assert b"1" in response.content


@pytest.mark.django_db
def test_alerts_panel_lists_and_acknowledges_active_alerts(client):
    user = User.objects.create_user("alerts", password="x", is_staff=True)
    alert = OperatorAlert.objects.create(
        type="production_stock_short",
        severity="warning",
        message="Insumo baixo",
    )

    client.force_login(user)
    panel = client.get("/gestor/alertas/painel/")
    assert panel.status_code == 200
    assert b"Insumo baixo" in panel.content

    ack = client.post(f"/gestor/alertas/{alert.pk}/ack/", HTTP_HX_REQUEST="true")
    assert ack.status_code == 200
    assert b"Insumo baixo" not in ack.content
    alert.refresh_from_db()
    assert alert.acknowledged is True


@pytest.mark.django_db
def test_operator_context_stays_empty_for_non_staff(rf):
    user = User.objects.create_user("customer", password="x")
    OperatorAlert.objects.create(type="stock_low", severity="critical", message="Estoque baixo")

    request = rf.get("/")
    request.user = user
    context = build_operator_context(request)

    assert context.is_active is False
    assert context.active_alerts_count == 0
    assert context.permissions.can_operate_pos is False
