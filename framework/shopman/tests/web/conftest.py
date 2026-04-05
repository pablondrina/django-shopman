"""Fixtures for storefront (channels.web) view tests."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from shopman.customers.models import Customer, CustomerAddress
from shopman.models import Shop
from shopman.offering.models import Collection, CollectionItem, Listing, ListingItem, Product
from shopman.ordering.models import Channel, Order, OrderItem


@pytest.fixture(autouse=True)
def shop_instance(db):
    """Create a default Shop singleton for all web tests."""
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

# ── Offering ──────────────────────────────────────────────────────────


@pytest.fixture
def collection(db):
    return Collection.objects.create(
        name="Pães", slug="paes", is_active=True, sort_order=1,
    )


@pytest.fixture
def collection_inactive(db):
    return Collection.objects.create(
        name="Sazonais", slug="sazonais", is_active=False, sort_order=99,
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
def product_unavailable(db):
    return Product.objects.create(
        sku="BOLO-ESPECIAL",
        name="Bolo Especial",
        base_price_q=5000,
        is_published=True,
        is_available=False,
    )


@pytest.fixture
def product_unpublished(db):
    return Product.objects.create(
        sku="RASCUNHO",
        name="Rascunho",
        base_price_q=100,
        is_published=False,
        is_available=True,
    )


@pytest.fixture
def croissant(db):
    return Product.objects.create(
        sku="CROISSANT",
        name="Croissant",
        base_price_q=800,
        is_published=True,
        is_available=True,
    )


@pytest.fixture
def collection_item(collection, product):
    return CollectionItem.objects.create(
        collection=collection, product=product, sort_order=1,
    )


@pytest.fixture
def listing(db):
    return Listing.objects.create(
        ref="balcao", name="Balcão", is_active=True, priority=10,
    )


@pytest.fixture
def listing_item(listing, product):
    return ListingItem.objects.create(
        listing=listing, product=product, price_q=90, is_published=True, is_available=True,
    )


# ── Ordering ──────────────────────────────────────────────────────────


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
def order(channel):
    return Order.objects.create(
        ref="ORD-001",
        channel=channel,
        status="new",
        total_q=1600,
        handle_type="phone",
        handle_ref="5543999990001",
        data={},
    )


@pytest.fixture
def order_with_payment(channel):
    return Order.objects.create(
        ref="ORD-PAY-001",
        channel=channel,
        status="new",
        total_q=2500,
        handle_type="phone",
        handle_ref="5543999990001",
        data={
            "payment": {
                "method": "pix",
                "status": "pending",
                "amount_q": 2500,
                "pix_code": "00020126...",
            },
        },
    )


@pytest.fixture
def order_paid(channel):
    return Order.objects.create(
        ref="ORD-PAID-001",
        channel=channel,
        status="confirmed",
        total_q=2500,
        handle_type="phone",
        handle_ref="5543999990001",
        data={
            "payment": {
                "method": "pix",
                "status": "captured",
                "amount_q": 2500,
            },
        },
    )


@pytest.fixture
def order_items(order, product, croissant):
    OrderItem.objects.create(
        order=order, line_id="line-1", sku=product.sku, name=product.name,
        qty=10, unit_price_q=80, line_total_q=800,
    )
    OrderItem.objects.create(
        order=order, line_id="line-2", sku=croissant.sku, name=croissant.name,
        qty=2, unit_price_q=800, line_total_q=1600,
    )
    return order


# ── Customers ─────────────────────────────────────────────────────────


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
        route="Rua das Flores",
        street_number="123",
        neighborhood="Centro",
        city="Londrina",
        is_default=True,
    )


# ── Cart helpers ──────────────────────────────────────────────────────


def _seed_stock_for_product_sku(sku: str) -> None:
    """Estoque pronto para testes de checkout (WP-S3 valida estoque no servidor)."""
    try:
        from shopman.stocking import stock
        from shopman.stocking.models import Position, PositionKind
    except ImportError:
        return
    try:
        position, _ = Position.objects.get_or_create(
            ref="loja",
            defaults={
                "name": "Loja Principal",
                "kind": PositionKind.PHYSICAL,
                "is_saleable": True,
            },
        )
        stock.receive(
            quantity=Decimal("1000"),
            sku=sku,
            position=position,
            target_date=date.today(),
            reason="web test seed stock",
        )
    except Exception:
        pass


@pytest.fixture
def cart_session(client, channel, product):
    """Add an item to the cart and return the client with active session."""
    _seed_stock_for_product_sku(product.sku)
    client.post("/cart/add/", {"sku": product.sku, "qty": 2})
    return client


@pytest.fixture
def cart_session_delivery(client, channel, croissant):
    """Cart with enough value for delivery (min R$ 20,00). Uses croissant (R$ 8,00 x 4 = R$ 32,00)."""
    _seed_stock_for_product_sku(croissant.sku)
    client.post("/cart/add/", {"sku": croissant.sku, "qty": 4})
    return client
