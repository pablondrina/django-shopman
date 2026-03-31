"""Tests for Cart/Checkout REST API (channels.api)."""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from shopman.offering.models import Product
from shopman.ordering.models import Channel, Order

from shop.models import Shop

pytestmark = pytest.mark.django_db


# ── Fixtures ─────────────────────────────────────────────────────────


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
        pricing_policy="external",
        edit_policy="open",
        config={},
    )


@pytest.fixture
def product(db):
    return Product.objects.create(
        sku="PAO-FRANCES",
        name="Pao Frances",
        base_price_q=80,
        is_published=True,
        is_available=True,
    )


@pytest.fixture
def product_unavailable(db):
    return Product.objects.create(
        sku="BOLO-ESPECIAL",
        name="Bolo Especial",
        base_price_q=5000,
        is_published=True,
        is_available=False,
    )


@pytest.fixture
def api_client():
    """DRF APIClient with session support."""
    client = APIClient()
    client.enforce_csrf_checks = False
    return client


@pytest.fixture
def api_cart(api_client, channel, product):
    """APIClient with one item already in the cart."""
    api_client.post("/api/cart/items/", {"sku": product.sku, "qty": 2}, format="json")
    return api_client


# ── GET /api/cart/ ───────────────────────────────────────────────────


class TestGetCart:
    def test_empty_cart(self, api_client):
        resp = api_client.get("/api/cart/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["subtotal_q"] == 0
        assert data["count"] == 0

    def test_cart_with_items(self, api_cart, product):
        resp = api_cart.get("/api/cart/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["sku"] == product.sku
        assert data["count"] == 2
        assert data["subtotal_q"] == 160  # 80 * 2

    def test_cart_returns_session_key(self, api_cart):
        resp = api_cart.get("/api/cart/")
        data = resp.json()
        assert "session_key" in data
        assert data["session_key"] is not None


# ── POST /api/cart/items/ ────────────────────────────────────────────


class TestAddItem:
    def test_add_item(self, api_client, channel, product):
        resp = api_client.post("/api/cart/items/", {"sku": product.sku, "qty": 1}, format="json")
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["sku"] == product.sku
        assert data["count"] == 1

    def test_add_item_default_qty(self, api_client, channel, product):
        resp = api_client.post("/api/cart/items/", {"sku": product.sku}, format="json")
        assert resp.status_code == 201
        data = resp.json()
        assert data["count"] == 1

    def test_add_item_merges_same_sku(self, api_client, channel, product):
        api_client.post("/api/cart/items/", {"sku": product.sku, "qty": 2}, format="json")
        resp = api_client.post("/api/cart/items/", {"sku": product.sku, "qty": 3}, format="json")
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["count"] == 5  # 2 + 3

    def test_add_item_nonexistent_sku(self, api_client, channel):
        resp = api_client.post("/api/cart/items/", {"sku": "NOPE", "qty": 1}, format="json")
        assert resp.status_code == 404
        assert "detail" in resp.json()

    def test_add_item_unavailable_product(self, api_client, channel, product_unavailable):
        resp = api_client.post(
            "/api/cart/items/", {"sku": product_unavailable.sku, "qty": 1}, format="json"
        )
        assert resp.status_code == 404

    def test_add_item_invalid_qty(self, api_client, channel, product):
        resp = api_client.post("/api/cart/items/", {"sku": product.sku, "qty": 0}, format="json")
        assert resp.status_code == 400

    def test_add_item_missing_sku(self, api_client, channel):
        resp = api_client.post("/api/cart/items/", {"qty": 1}, format="json")
        assert resp.status_code == 400


# ── PATCH /api/cart/items/{line_id}/ ─────────────────────────────────


class TestUpdateItem:
    def test_update_qty(self, api_cart, channel, product):
        # Get current cart to find line_id
        cart = api_cart.get("/api/cart/").json()
        line_id = cart["items"][0]["line_id"]

        resp = api_cart.patch(f"/api/cart/items/{line_id}/", {"qty": 5}, format="json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 5
        assert data["subtotal_q"] == 400  # 80 * 5

    def test_update_invalid_qty(self, api_cart, channel, product):
        cart = api_cart.get("/api/cart/").json()
        line_id = cart["items"][0]["line_id"]

        resp = api_cart.patch(f"/api/cart/items/{line_id}/", {"qty": 0}, format="json")
        assert resp.status_code == 400

    def test_update_no_cart(self, api_client, channel):
        resp = api_client.patch("/api/cart/items/fake-line/", {"qty": 2}, format="json")
        assert resp.status_code == 404


# ── DELETE /api/cart/items/{line_id}/ ────────────────────────────────


class TestRemoveItem:
    def test_remove_item(self, api_cart, channel, product):
        cart = api_cart.get("/api/cart/").json()
        line_id = cart["items"][0]["line_id"]

        resp = api_cart.delete(f"/api/cart/items/{line_id}/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["count"] == 0

    def test_remove_no_cart(self, api_client, channel):
        resp = api_client.delete("/api/cart/items/fake-line/")
        assert resp.status_code == 404


# ── POST /api/checkout/ ─────────────────────────────────────────────


class TestCheckout:
    def test_checkout_success(self, api_cart, channel, product):
        resp = api_cart.post(
            "/api/checkout/",
            {"name": "Joao Silva", "phone": "43999990001"},
            format="json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "order_ref" in data
        assert "order_id" in data
        assert data["status"] == "committed"

        # Verify order was created in DB
        assert Order.objects.filter(ref=data["order_ref"]).exists()

    def test_checkout_with_notes_and_delivery(self, api_cart, channel, product):
        resp = api_cart.post(
            "/api/checkout/",
            {
                "name": "Maria Santos",
                "phone": "43999990002",
                "notes": "Sem cebola",
                "fulfillment_type": "delivery",
                "delivery_address": "Rua das Flores 123",
            },
            format="json",
        )
        assert resp.status_code == 201

    def test_checkout_empty_cart(self, api_client, channel):
        resp = api_client.post(
            "/api/checkout/",
            {"name": "Joao", "phone": "43999990001"},
            format="json",
        )
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    def test_checkout_missing_name(self, api_cart, channel, product):
        resp = api_cart.post(
            "/api/checkout/",
            {"phone": "43999990001"},
            format="json",
        )
        assert resp.status_code == 400

    def test_checkout_missing_phone(self, api_cart, channel, product):
        resp = api_cart.post(
            "/api/checkout/",
            {"name": "Joao"},
            format="json",
        )
        assert resp.status_code == 400

    def test_checkout_clears_cart(self, api_cart, channel, product):
        api_cart.post(
            "/api/checkout/",
            {"name": "Joao", "phone": "43999990001"},
            format="json",
        )
        # Cart should be empty after checkout
        resp = api_cart.get("/api/cart/")
        data = resp.json()
        assert data["items"] == []
        assert data["count"] == 0

    def test_checkout_default_fulfillment_is_pickup(self, api_cart, channel, product):
        resp = api_cart.post(
            "/api/checkout/",
            {"name": "Joao", "phone": "43999990001"},
            format="json",
        )
        assert resp.status_code == 201
        order = Order.objects.get(ref=resp.json()["order_ref"])
        assert order.data.get("fulfillment_type") == "pickup"

    def test_checkout_invalid_fulfillment_type(self, api_cart, channel, product):
        resp = api_cart.post(
            "/api/checkout/",
            {"name": "Joao", "phone": "43999990001", "fulfillment_type": "drone"},
            format="json",
        )
        assert resp.status_code == 400
