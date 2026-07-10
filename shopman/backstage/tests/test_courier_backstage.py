"""Backstage: bloco courier na projection do pedido + ações do operador.

Cobre a superfície REST que o Gestor de Pedidos (orders-nuxt) consome:
GET orders/<ref>/ (bloco ``courier``) e as ações courier-dispatch /
courier-cancel / courier-quote. Usa o adapter mock — sem rede.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from shopman.orderman.models import Directive, Order, OrderItem

from shopman.shop.adapters import courier_mock
from shopman.shop.directives import COURIER_DISPATCH
from shopman.shop.models import Shop
from shopman.shop.services import courier

pytestmark = pytest.mark.django_db

MOCK_ADAPTER = "shopman.shop.adapters.courier_mock"


@pytest.fixture(autouse=True)
def _clean_state():
    courier_mock.reset()
    cache.clear()
    yield
    courier_mock.reset()


@pytest.fixture
def shop(db):
    return Shop.objects.create(
        name="Loja",
        route="Rua da Loja",
        street_number="10",
        city="Londrina",
        state_code="PR",
        latitude=-23.34,
        longitude=-51.15,
    )


@pytest.fixture
def operator(db, shop):
    perm = Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"),
        codename="manage_orders",
    )
    user = User.objects.create_user("courier-op", password="pw", is_staff=True)
    user.user_permissions.add(perm)
    return user


def _delivery_order(ref="CRB-1", status=Order.Status.READY, **data_extra) -> Order:
    data = {
        "fulfillment_type": "delivery",
        "customer": {"name": "Ana", "phone": "5543999990000"},
        "payment": {"method": "cash"},
        "delivery_address_structured": {
            "route": "Rua das Flores",
            "street_number": "123",
            "city": "Londrina",
            "state_code": "PR",
            "formatted_address": "Rua das Flores 123",
            "latitude": -23.31,
            "longitude": -51.16,
        },
    }
    data.update(data_extra)
    order = Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"S-{ref}", status=status,
        snapshot={"items": []}, total_q=1500, data=data,
    )
    OrderItem.objects.create(
        order=order, line_id="1", sku="SKU", name="Produto", qty=1,
        unit_price_q=1500, line_total_q=1500,
    )
    return order


def _detail(client, ref):
    return client.get(reverse("api-backstage-order-detail", args=[ref])).json()["order"]


# ── Projection ──────────────────────────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_detail_shows_courier_block_with_dispatch_available(client, operator, shop):
    order = _delivery_order()
    client.force_login(operator)
    block = _detail(client, order.ref)["courier"]
    assert block["can_quote"] is True
    assert block["can_dispatch"] is True
    assert block["can_cancel"] is False
    assert block["status"] == ""
    assert block["attempts_count"] == 0


def test_detail_courier_none_without_adapter_or_ride(client, operator, shop):
    order = _delivery_order()
    client.force_login(operator)
    assert _detail(client, order.ref)["courier"] is None


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_detail_courier_none_for_pickup(client, operator, shop):
    order = _delivery_order(ref="CRB-P", fulfillment_type="pickup")
    client.force_login(operator)
    assert _detail(client, order.ref)["courier"] is None


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_detail_active_ride_shows_driver_and_labels(client, operator, shop):
    order = _delivery_order()
    courier.request_dispatch(order, actor="test")
    from shopman.shop.handlers.courier_dispatch import CourierDispatchHandler

    directive = Directive.objects.get(topic=COURIER_DISPATCH)
    CourierDispatchHandler().handle(message=directive, ctx={})
    order.refresh_from_db()
    courier.apply_status(order, "A", source="poll")

    client.force_login(operator)
    block = _detail(client, order.ref)["courier"]
    assert block["status"] == "A"
    assert block["status_label"] == "Entregador a caminho da loja"
    assert block["active"] is True
    assert block["driver"]["name"] == "Entregador Mock"
    assert block["tracking_url"].startswith("https://rastreio.mock/")
    assert block["estimate_display"].startswith("R$ 12,50")
    assert block["can_cancel"] is True
    assert block["can_dispatch"] is False


# ── Ações ───────────────────────────────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_courier_dispatch_action_queues_directive(client, operator, shop):
    order = _delivery_order()
    client.force_login(operator)
    resp = client.post(reverse("api-backstage-order-courier-dispatch", args=[order.ref]))
    assert resp.status_code == 200
    assert Directive.objects.filter(topic=COURIER_DISPATCH, payload__order_ref=order.ref).exists()


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_courier_dispatch_blocked_for_wrong_status(client, operator, shop):
    order = _delivery_order(status=Order.Status.PREPARING)
    client.force_login(operator)
    resp = client.post(reverse("api-backstage-order-courier-dispatch", args=[order.ref]))
    assert resp.status_code == 400
    assert "pronto" in resp.json()["detail"]


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_courier_cancel_action(client, operator, shop):
    order = _delivery_order()
    courier.request_dispatch(order, actor="test")
    from shopman.shop.handlers.courier_dispatch import CourierDispatchHandler

    CourierDispatchHandler().handle(message=Directive.objects.get(topic=COURIER_DISPATCH), ctx={})
    order.refresh_from_db()

    client.force_login(operator)
    resp = client.post(reverse("api-backstage-order-courier-cancel", args=[order.ref]))
    assert resp.status_code == 200
    order.refresh_from_db()
    assert not courier.has_active_ride(order)


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_courier_cancel_without_active_ride_fails(client, operator, shop):
    order = _delivery_order()
    client.force_login(operator)
    resp = client.post(reverse("api-backstage-order-courier-cancel", args=[order.ref]))
    assert resp.status_code == 400


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_courier_quote_action_returns_and_stores_estimate(client, operator, shop):
    order = _delivery_order()
    client.force_login(operator)
    resp = client.post(reverse("api-backstage-order-courier-quote", args=[order.ref]))
    assert resp.status_code == 200
    quote = resp.json()["quote"]
    assert quote["value_q"] == 1250
    assert quote["value_display"] == "R$ 12,50"
    order.refresh_from_db()
    assert courier.get_block(order)["estimate"]["value_q"] == 1250


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_courier_quote_unavailable_without_coordinates(client, operator, shop):
    order = _delivery_order(delivery_address_structured={"city": "Londrina"})
    client.force_login(operator)
    resp = client.post(reverse("api-backstage-order-courier-quote", args=[order.ref]))
    assert resp.status_code == 400


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_courier_actions_require_manage_orders(client, shop):
    order = _delivery_order()
    plain = User.objects.create_user("plain", password="pw", is_staff=True)
    client.force_login(plain)
    for name in ("courier-dispatch", "courier-cancel", "courier-quote"):
        resp = client.post(reverse(f"api-backstage-order-{name}", args=[order.ref]))
        assert resp.status_code == 403, name


# ── Card do board ───────────────────────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_board_card_carries_courier_badge(client, operator, shop):
    order = _delivery_order(
        courier={"provider": "machine", "id_mch": "1", "status": "E"},
    )
    Order.objects.filter(pk=order.pk).update(status=Order.Status.DISPATCHED)
    client.force_login(operator)
    resp = client.get(reverse("api-backstage-orders"))
    cards = resp.json()["queue"]["saida_delivery_transit"]
    assert cards[0]["courier_status"] == "E"
    assert cards[0]["courier_status_label"] == "Saiu para entrega"
