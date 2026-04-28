"""Backstage SSE publisher tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from shopman.backstage.models import OperatorAlert
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
from shopman.orderman.models import Order
from shopman.shop.models import Channel, Shop


@pytest.fixture
def channel(db):
    return Channel.objects.create(ref="web", name="Web", is_active=True)


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        ref="sse-prod-v1",
        name="SSE Produto",
        output_sku="SSE-PROD",
        batch_size=Decimal("10"),
    )


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_order_change_publishes_backstage_orders_event(mock_send, channel):
    order = Order.objects.create(ref="SSE-ORD-1", channel_ref=channel.ref, status=Order.Status.NEW, total_q=1000)

    order.transition_status(Order.Status.CONFIRMED, actor="test")

    assert any(
        call.args[0] == "backstage-orders-main"
        and call.args[1] == "backstage-orders-update"
        and call.args[2]["ref"] == "SSE-ORD-1"
        for call in mock_send.call_args_list
    )


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_production_change_publishes_backstage_production_event(mock_send, recipe):
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")

    assert any(
        call.args[0] == "backstage-production-main"
        and call.args[1] == "backstage-production-update"
        and call.args[2]["ref"] == work_order.ref
        for call in mock_send.call_args_list
    )


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_operator_alert_publishes_backstage_alerts_event(mock_send):
    alert = OperatorAlert.objects.create(
        type="production_late",
        severity="warning",
        message="Produção atrasada",
    )

    assert any(
        call.args[0] == "backstage-alerts-main"
        and call.args[1] == "backstage-alerts-update"
        and call.args[2]["id"] == alert.pk
        for call in mock_send.call_args_list
    )


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_order_change_publishes_shop_scoped_backstage_event(mock_send):
    shop = Shop.objects.create(name="SSE Loja")
    channel = Channel.objects.create(ref="web-scoped", name="Web Scoped", shop=shop, is_active=True)
    order = Order.objects.create(
        ref="SSE-ORD-SCOPED",
        channel_ref=channel.ref,
        status=Order.Status.NEW,
        total_q=1000,
    )

    order.transition_status(Order.Status.CONFIRMED, actor="test")

    channels = [call.args[0] for call in mock_send.call_args_list]
    assert "backstage-orders-main" in channels
    assert f"backstage-orders-shop-{shop.pk}" in channels


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_production_change_publishes_shop_scoped_backstage_event(mock_send, recipe):
    shop = Shop.objects.create(name="SSE Producao")

    craft.plan(recipe, 10, date=date.today(), position_ref="forno")

    channels = [call.args[0] for call in mock_send.call_args_list]
    assert "backstage-production-main" in channels
    assert f"backstage-production-shop-{shop.pk}" in channels
