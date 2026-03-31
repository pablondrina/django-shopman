"""Tests for WP-F10.3: POS Mode (Balcao)."""
from __future__ import annotations

import json
import re
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import Client
from shopman.customers.models import Customer
from shopman.offering.models import Collection, CollectionItem, Listing, ListingItem, Product
from shopman.ordering.models import Channel, Order

from channels.presets import pos
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
def balcao_channel(db):
    return Channel.objects.create(
        ref="balcao",
        name="Balcao / PDV",
        listing_ref="balcao",
        pricing_policy="internal",
        edit_policy="open",
        config=pos(),
    )


@pytest.fixture
def products(db):
    col_paes = Collection.objects.create(slug="paes", name="Paes", is_active=True, sort_order=1)
    col_cafe = Collection.objects.create(slug="cafe", name="Cafe", is_active=True, sort_order=2)

    pao = Product.objects.create(sku="PAO-FRANCES", name="Pao Frances", base_price_q=150, is_published=True, is_available=True)
    croissant = Product.objects.create(sku="CROISSANT", name="Croissant", base_price_q=800, is_published=True, is_available=True)
    cafe = Product.objects.create(sku="CAFE-ESPRESSO", name="Cafe Espresso", base_price_q=500, is_published=True, is_available=True)

    CollectionItem.objects.create(collection=col_paes, product=pao, is_primary=True)
    CollectionItem.objects.create(collection=col_paes, product=croissant, is_primary=True)
    CollectionItem.objects.create(collection=col_cafe, product=cafe, is_primary=True)

    listing = Listing.objects.create(ref="balcao", name="Balcao", is_active=True, priority=10)
    ListingItem.objects.create(listing=listing, product=pao, price_q=150, is_published=True, is_available=True)
    ListingItem.objects.create(listing=listing, product=croissant, price_q=800, is_published=True, is_available=True)
    ListingItem.objects.create(listing=listing, product=cafe, price_q=500, is_published=True, is_available=True)

    return {"pao": pao, "croissant": croissant, "cafe": cafe}


@pytest.fixture
def customer(db):
    return Customer.objects.create(
        ref="CLI-POS-001",
        first_name="Maria",
        last_name="Santos",
        phone="+5543991111111",
    )


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(username="operador", password="test1234", is_staff=True)


@pytest.fixture
def staff_client(staff_user):
    client = Client()
    client.login(username="operador", password="test1234")
    return client


def _close_payload(items, **kwargs):
    """Build POST data for pos_close (HTMX sends payload as form field)."""
    body = {"items": items, "payment_method": kwargs.get("payment_method", "dinheiro")}
    if kwargs.get("customer_name"):
        body["customer_name"] = kwargs["customer_name"]
    if kwargs.get("customer_phone"):
        body["customer_phone"] = kwargs["customer_phone"]
    return {"payload": json.dumps(body)}


def _extract_order_ref(html):
    """Extract order_ref from pos-result data attribute."""
    m = re.search(r'data-order-ref="([^"]+)"', html)
    return m.group(1) if m else None


# ── TestPOSAccess ───────────────────────────────────────────────────


class TestPOSAccess:
    def test_requires_staff(self, client, balcao_channel, products):
        resp = client.get("/gestao/pos/")
        assert resp.status_code == 302
        assert "/admin/login/" in resp.url

    def test_staff_can_access(self, staff_client, balcao_channel, products):
        resp = staff_client.get("/gestao/pos/")
        assert resp.status_code == 200


# ── TestPOSView ─────────────────────────────────────────────────────


class TestPOSView:
    def test_shows_products(self, staff_client, balcao_channel, products):
        resp = staff_client.get("/gestao/pos/")
        content = resp.content.decode()
        assert "PAO-FRANCES" in content
        assert "CROISSANT" in content
        assert "CAFE-ESPRESSO" in content

    def test_shows_collections(self, staff_client, balcao_channel, products):
        resp = staff_client.get("/gestao/pos/")
        content = resp.content.decode()
        assert "Paes" in content
        assert "Cafe" in content


# ── TestPOSCustomerLookup (HTMX: returns HTML partial) ─────────────


class TestPOSCustomerLookup:
    def test_customer_found(self, staff_client, balcao_channel, customer):
        resp = staff_client.post("/gestao/pos/customer-lookup/", {"phone": "43991111111"})
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Maria" in content
        assert "CLI-POS-001" in content

    def test_customer_not_found(self, staff_client, balcao_channel):
        resp = staff_client.post("/gestao/pos/customer-lookup/", {"phone": "43900000000"})
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "n&atilde;o encontrado" in content or "não encontrado" in content


# ── TestPOSClose (HTMX: returns HTML partial with data attributes) ──


class TestPOSClose:
    def test_close_creates_order(self, staff_client, balcao_channel, products):
        resp = staff_client.post("/gestao/pos/close/", _close_payload([
            {"sku": "PAO-FRANCES", "qty": 3, "unit_price_q": 150},
            {"sku": "CAFE-ESPRESSO", "qty": 1, "unit_price_q": 500},
        ]))
        assert resp.status_code == 200
        html = resp.content.decode()
        order_ref = _extract_order_ref(html)
        assert order_ref is not None

        order = Order.objects.get(ref=order_ref)
        assert order.channel.ref == "balcao"

    def test_close_empty_cart_fails(self, staff_client, balcao_channel):
        resp = staff_client.post("/gestao/pos/close/", _close_payload([]))
        assert resp.status_code == 422

    def test_close_correct_total(self, staff_client, balcao_channel, products):
        resp = staff_client.post("/gestao/pos/close/", _close_payload([
            {"sku": "PAO-FRANCES", "qty": 5, "unit_price_q": 150},
        ]))
        order_ref = _extract_order_ref(resp.content.decode())
        order = Order.objects.get(ref=order_ref)
        assert order.total_q == 750  # 5 x R$ 1,50

    def test_close_auto_confirms(self, staff_client, balcao_channel, products):
        """POS orders should auto-confirm (immediate mode)."""
        resp = staff_client.post("/gestao/pos/close/", _close_payload([
            {"sku": "CROISSANT", "qty": 1, "unit_price_q": 800},
        ]))
        order_ref = _extract_order_ref(resp.content.decode())
        order = Order.objects.get(ref=order_ref)
        assert order.status in ("new", "confirmed")

    def test_close_with_customer(self, staff_client, balcao_channel, products, customer):
        resp = staff_client.post("/gestao/pos/close/", _close_payload(
            [{"sku": "PAO-FRANCES", "qty": 2, "unit_price_q": 150}],
            customer_name="Maria Santos",
            customer_phone="43991111111",
        ))
        order_ref = _extract_order_ref(resp.content.decode())
        order = Order.objects.get(ref=order_ref)
        assert order.data.get("customer", {}).get("name") == "Maria Santos"
