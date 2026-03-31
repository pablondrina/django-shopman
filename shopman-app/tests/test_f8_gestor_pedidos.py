"""Tests for WP-F8: Gestor de Pedidos (operator dashboard)."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client
from shopman.ordering.models import Channel, Order, OrderItem

from shop.models import Shop


@pytest.fixture(autouse=True)
def shop_instance(db):
    return Shop.objects.create(
        name="Nelson Boulangerie",
        brand_name="Nelson Boulangerie",
        short_name="Nelson",
        tagline="Padaria Artesanal",
        primary_color="#C5A55A",
        default_ddd="43",
        city="Londrina",
        state_code="PR",
    )


@pytest.fixture
def channel(db):
    return Channel.objects.create(
        ref="web",
        name="Loja Online",
        listing_ref="balcao",
        pricing_policy="external",
        edit_policy="open",
        config={},
    )


@pytest.fixture
def whatsapp_channel(db):
    return Channel.objects.create(
        ref="whatsapp",
        name="WhatsApp",
        listing_ref="balcao",
        pricing_policy="external",
        edit_policy="open",
        config={},
    )


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="operador", password="test1234", is_staff=True,
    )


@pytest.fixture
def normal_user(db):
    return User.objects.create_user(
        username="cliente", password="test1234", is_staff=False,
    )


@pytest.fixture
def staff_client(staff_user):
    client = Client()
    client.login(username="operador", password="test1234")
    return client


@pytest.fixture
def order_new(channel):
    return Order.objects.create(
        ref="ORD-F8-001",
        channel=channel,
        status="new",
        total_q=1600,
        handle_type="phone",
        handle_ref="5543999990001",
        data={"customer_name": "João Silva"},
    )


@pytest.fixture
def order_confirmed(channel):
    o = Order.objects.create(
        ref="ORD-F8-002",
        channel=channel,
        status="new",
        total_q=2500,
        handle_type="phone",
        handle_ref="5543999990002",
        data={"customer_name": "Maria Santos"},
    )
    o.transition_status("confirmed", actor="test")
    return o


@pytest.fixture
def order_processing(channel):
    o = Order.objects.create(
        ref="ORD-F8-003",
        channel=channel,
        status="new",
        total_q=800,
        handle_type="phone",
        handle_ref="5543999990003",
        data={},
    )
    o.transition_status("confirmed", actor="test")
    o.transition_status("processing", actor="test")
    return o


@pytest.fixture
def order_with_items(order_new):
    OrderItem.objects.create(
        order=order_new, line_id="line-1", sku="PAO-FRANCES", name="Pão Francês",
        qty=10, unit_price_q=80, line_total_q=800,
    )
    OrderItem.objects.create(
        order=order_new, line_id="line-2", sku="CROISSANT", name="Croissant",
        qty=2, unit_price_q=400, line_total_q=800,
    )
    return order_new


# ── Access ───────────────────────────────────────────────────────────


class TestGestorAccess:
    def test_requires_staff(self, client, db):
        resp = client.get("/pedidos/")
        assert resp.status_code == 302
        assert "/admin/login/" in resp.url

    def test_non_staff_redirected(self, normal_user):
        client = Client()
        client.login(username="cliente", password="test1234")
        resp = client.get("/pedidos/")
        assert resp.status_code == 302
        assert "/admin/login/" in resp.url

    def test_staff_can_access(self, staff_client, order_new):
        resp = staff_client.get("/pedidos/")
        assert resp.status_code == 200
        assert "Gestor de Pedidos" in resp.content.decode() or "Pedidos" in resp.content.decode()


# ── List & Filters ───────────────────────────────────────────────────


class TestGestorList:
    def test_shows_new_orders(self, staff_client, order_new):
        resp = staff_client.get("/pedidos/")
        content = resp.content.decode()
        assert order_new.ref in content

    def test_filters_by_status(self, staff_client, order_new, order_confirmed):
        # Filter by confirmed
        resp = staff_client.get("/pedidos/?filter=confirmed")
        content = resp.content.decode()
        assert order_confirmed.ref in content
        assert order_new.ref not in content

    def test_filter_all_shows_everything(self, staff_client, order_new, order_confirmed):
        resp = staff_client.get("/pedidos/?filter=all")
        content = resp.content.decode()
        assert order_new.ref in content
        assert order_confirmed.ref in content

    def test_multichannel_badges(self, staff_client, channel, whatsapp_channel):
        Order.objects.create(
            ref="ORD-WEB", channel=channel, status="new", total_q=100, data={},
        )
        Order.objects.create(
            ref="ORD-WA", channel=whatsapp_channel, status="new", total_q=200, data={},
        )
        resp = staff_client.get("/pedidos/")
        content = resp.content.decode()
        assert "ORD-WEB" in content
        assert "ORD-WA" in content

    def test_list_partial(self, staff_client, order_new):
        resp = staff_client.get("/pedidos/list/?filter=all")
        assert resp.status_code == 200
        assert order_new.ref in resp.content.decode()


# ── Actions ──────────────────────────────────────────────────────────


class TestGestorActions:
    def test_confirm_order(self, staff_client, order_new):
        resp = staff_client.post(f"/pedidos/{order_new.ref}/confirm/")
        assert resp.status_code == 200
        order_new.refresh_from_db()
        assert order_new.status == "confirmed"

    def test_confirm_non_new_fails(self, staff_client, order_confirmed):
        resp = staff_client.post(f"/pedidos/{order_confirmed.ref}/confirm/")
        assert resp.status_code == 422

    def test_reject_requires_reason(self, staff_client, order_new):
        resp = staff_client.post(f"/pedidos/{order_new.ref}/reject/", {"reason": ""})
        assert resp.status_code == 422

    def test_reject_with_reason(self, staff_client, order_new):
        resp = staff_client.post(
            f"/pedidos/{order_new.ref}/reject/",
            {"reason": "Sem estoque"},
        )
        assert resp.status_code == 200
        order_new.refresh_from_db()
        assert order_new.status == "cancelled"
        assert order_new.data["cancellation_reason"] == "Sem estoque"
        assert order_new.data["rejected_by"] == "operador"

    def test_advance_confirmed_to_processing(self, staff_client, order_confirmed):
        resp = staff_client.post(f"/pedidos/{order_confirmed.ref}/advance/")
        assert resp.status_code == 200
        order_confirmed.refresh_from_db()
        assert order_confirmed.status == "processing"

    def test_advance_processing_to_ready(self, staff_client, order_processing):
        resp = staff_client.post(f"/pedidos/{order_processing.ref}/advance/")
        assert resp.status_code == 200
        order_processing.refresh_from_db()
        assert order_processing.status == "ready"

    def test_internal_notes_saved(self, staff_client, order_new):
        resp = staff_client.post(
            f"/pedidos/{order_new.ref}/notes/",
            {"notes": "Cliente pediu sem glúten"},
        )
        assert resp.status_code == 200
        order_new.refresh_from_db()
        assert order_new.data["internal_notes"] == "Cliente pediu sem glúten"


# ── Detail ───────────────────────────────────────────────────────────


class TestGestorDetail:
    def test_detail_shows_items(self, staff_client, order_with_items):
        resp = staff_client.get(f"/pedidos/{order_with_items.ref}/detail/")
        content = resp.content.decode()
        assert resp.status_code == 200
        assert "Pão Francês" in content
        assert "Croissant" in content

    def test_detail_shows_timeline(self, staff_client, order_confirmed):
        resp = staff_client.get(f"/pedidos/{order_confirmed.ref}/detail/")
        assert resp.status_code == 200
        assert "Histórico" in resp.content.decode() or "Confirmado" in resp.content.decode()
