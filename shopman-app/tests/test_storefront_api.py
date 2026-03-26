"""Tests for Storefront REST API: catalog, tracking, account (WP-E6)."""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient
from shopman.customers.models import Customer, CustomerAddress
from shopman.offering.models import Collection, CollectionItem, Product
from shopman.ordering.models import Channel, Order, OrderItem

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
        background_color="#F5F0EB",
        default_ddd="43",
        city="Londrina",
        state_code="PR",
        whatsapp="5543999999999",
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
def collection(db):
    return Collection.objects.create(
        name="Pães", slug="paes", is_active=True, sort_order=1,
    )


@pytest.fixture
def product(db):
    return Product.objects.create(
        sku="PAO-FRANCES",
        name="Pão Francês",
        base_price_q=80,
        is_published=True,
        is_available=True,
    )


@pytest.fixture
def product2(db):
    return Product.objects.create(
        sku="CROISSANT",
        name="Croissant",
        base_price_q=800,
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
def collection_item(collection, product):
    return CollectionItem.objects.create(
        collection=collection, product=product, sort_order=1,
    )


@pytest.fixture
def order(channel, customer):
    return Order.objects.create(
        ref="ORD-API-001",
        channel=channel,
        status="confirmed",
        total_q=1600,
        handle_type="phone",
        handle_ref=customer.phone,  # Use normalized phone from customer
        data={"payment": {"method": "pix", "status": "captured"}},
    )


@pytest.fixture
def order_items(order, product, product2):
    OrderItem.objects.create(
        order=order, line_id="line-1", sku=product.sku, name=product.name,
        qty=10, unit_price_q=80, line_total_q=800,
    )
    OrderItem.objects.create(
        order=order, line_id="line-2", sku=product2.sku, name=product2.name,
        qty=1, unit_price_q=800, line_total_q=800,
    )
    return order


@pytest.fixture
def customer(db):
    return Customer.objects.create(
        ref="CUST-001",
        first_name="João",
        last_name="Silva",
        phone="5543999990001",
    )


@pytest.fixture
def customer_address(customer):
    return CustomerAddress.objects.create(
        customer=customer,
        label="home",
        formatted_address="Rua das Flores 123 - Centro - Londrina",
        is_default=True,
    )


@pytest.fixture
def api_client():
    client = APIClient()
    client.enforce_csrf_checks = False
    return client


@pytest.fixture
def authenticated_client(api_client, customer):
    """APIClient with Django auth for customer."""
    from shopman.auth.protocols.customer import AuthCustomerInfo
    from shopman.auth.services._user_bridge import get_or_create_user_for_customer

    info = AuthCustomerInfo(
        uuid=customer.uuid,
        name=customer.name,
        phone=customer.phone,
        email=None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    api_client.force_login(user, backend="shopman.auth.backends.PhoneOTPBackend")
    return api_client


# ── Catalog: ProductListView ─────────────────────────────────────────


class TestCatalogProductList:
    def test_lists_products_with_prices(self, api_client, product, product2):
        resp = api_client.get("/api/catalog/products/")
        assert resp.status_code == 200
        data = resp.json()
        results = data.get("results", data)
        assert len(results) == 2
        skus = {item["sku"] for item in results}
        assert "PAO-FRANCES" in skus
        assert "CROISSANT" in skus
        # Each product has price info
        for item in results:
            assert "price_q" in item
            assert "badge" in item

    def test_filters_by_collection(self, api_client, product, product2, collection, collection_item):
        resp = api_client.get("/api/catalog/products/?collection=paes")
        assert resp.status_code == 200
        data = resp.json()
        results = data.get("results", data)
        assert len(results) == 1
        assert results[0]["sku"] == "PAO-FRANCES"

    def test_search_by_name(self, api_client, product, product2):
        resp = api_client.get("/api/catalog/products/?search=Croissant")
        assert resp.status_code == 200
        data = resp.json()
        results = data.get("results", data)
        assert len(results) == 1
        assert results[0]["sku"] == "CROISSANT"

    def test_excludes_unpublished(self, api_client, product):
        Product.objects.create(
            sku="DRAFT", name="Draft", base_price_q=100,
            is_published=False, is_available=True,
        )
        resp = api_client.get("/api/catalog/products/")
        data = resp.json()
        results = data.get("results", data)
        skus = {item["sku"] for item in results}
        assert "DRAFT" not in skus

    def test_available_filter(self, api_client, product, product_unavailable):
        resp = api_client.get("/api/catalog/products/?available=true")
        data = resp.json()
        results = data.get("results", data)
        skus = {item["sku"] for item in results}
        assert "PAO-FRANCES" in skus
        assert "BOLO-ESPECIAL" not in skus


# ── Catalog: ProductDetailView ───────────────────────────────────────


class TestCatalogProductDetail:
    def test_returns_product_detail(self, api_client, product):
        resp = api_client.get(f"/api/catalog/products/{product.sku}/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sku"] == product.sku
        assert data["name"] == product.name
        assert "price_q" in data
        assert "badge" in data
        assert "alternatives" in data

    def test_not_found(self, api_client):
        resp = api_client.get("/api/catalog/products/NONEXISTENT/")
        assert resp.status_code == 404


# ── Catalog: CollectionListView ──────────────────────────────────────


class TestCatalogCollections:
    def test_lists_collections(self, api_client, collection, collection_item):
        resp = api_client.get("/api/catalog/collections/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["slug"] == "paes"
        assert data[0]["product_count"] == 1

    def test_excludes_inactive(self, api_client, collection):
        Collection.objects.create(name="Hidden", slug="hidden", is_active=False)
        resp = api_client.get("/api/catalog/collections/")
        data = resp.json()
        slugs = {c["slug"] for c in data}
        assert "hidden" not in slugs


# ── Tracking ─────────────────────────────────────────────────────────


class TestTrackingAPI:
    def test_returns_order_status(self, api_client, order, order_items):
        resp = api_client.get(f"/api/tracking/{order.ref}/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ref"] == order.ref
        assert data["status"] == "confirmed"
        assert data["status_label"] == "Confirmado"
        assert len(data["items"]) == 2
        assert data["payment_status"] == "captured"

    def test_not_found(self, api_client):
        resp = api_client.get("/api/tracking/NONEXISTENT/")
        assert resp.status_code == 404


# ── Account ──────────────────────────────────────────────────────────


class TestAccountAPI:
    def test_profile_requires_auth(self, api_client):
        resp = api_client.get("/api/account/profile/")
        assert resp.status_code == 401

    def test_profile_returns_data(self, authenticated_client, customer):
        resp = authenticated_client.get("/api/account/profile/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ref"] == customer.ref
        assert data["name"] == customer.name

    def test_addresses_requires_auth(self, api_client):
        resp = api_client.get("/api/account/addresses/")
        assert resp.status_code == 401

    def test_addresses_returns_data(self, authenticated_client, customer_address):
        resp = authenticated_client.get("/api/account/addresses/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["formatted_address"] == customer_address.formatted_address
        assert data[0]["is_default"] is True

    def test_orders_requires_auth(self, api_client):
        resp = api_client.get("/api/account/orders/")
        assert resp.status_code == 401

    def test_orders_returns_history(self, authenticated_client, customer, order):
        resp = authenticated_client.get("/api/account/orders/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["ref"] == order.ref
        assert data[0]["status_label"] == "Confirmado"
