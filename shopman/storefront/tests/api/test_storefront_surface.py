from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product

from shopman.shop.models import Channel, Shop

pytestmark = pytest.mark.django_db


def test_api_storefront_menu_returns_projection_contract(client):
    product = _seed_surface()

    resp = client.get("/api/v1/storefront/menu/")

    assert resp.status_code == 200
    data = resp.json()
    assert data["catalog"]["has_items"] is True
    assert data["catalog"]["items"][0]["sku"] == product.sku
    assert data["catalog"]["items"][0]["availability"] in {
        "available",
        "low_stock",
        "planned_ok",
        "unavailable",
    }
    assert data["cart"]["is_empty"] is True


def test_api_cart_sku_qty_sets_absolute_qty_and_returns_cart_projection(client):
    product = _seed_surface(stock_qty=Decimal("10"))

    add = client.put(
        f"/api/v1/cart/skus/{product.sku}/",
        data=json.dumps({"qty": 2}),
        content_type="application/json",
    )

    assert add.status_code == 200
    add_data = add.json()
    assert add_data["ok"] is True
    assert add_data["line"]["qty"] == 2
    assert add_data["summary"]["count"] == 2
    assert add_data["cart"]["items_count"] == 2
    assert add_data["cart"]["items"][0]["sku"] == product.sku

    remove = client.put(
        f"/api/v1/cart/skus/{product.sku}/",
        data=json.dumps({"qty": 0}),
        content_type="application/json",
    )

    assert remove.status_code == 200
    remove_data = remove.json()
    assert remove_data["line"]["qty"] == 0
    assert remove_data["cart"]["is_empty"] is True


def _seed_surface(*, stock_qty: Decimal | None = None) -> Product:
    Shop.objects.create(
        name="Demo Bakery",
        brand_name="Demo Bakery",
        short_name="Demo",
    )
    Channel.objects.create(ref="web", name="Loja Online")
    listing = Listing.objects.create(ref="web", name="Web", is_active=True, priority=10)
    collection = Collection.objects.create(name="Pães", ref="paes", is_active=True, sort_order=1)
    product = Product.objects.create(
        sku="PAO-FRANCES",
        name="Pão Francês",
        base_price_q=90,
        is_published=True,
        is_sellable=True,
    )
    CollectionItem.objects.create(collection=collection, product=product, sort_order=1)
    ListingItem.objects.create(
        listing=listing,
        product=product,
        price_q=90,
        is_published=True,
        is_sellable=True,
    )
    if stock_qty is not None:
        _seed_stock(product.sku, stock_qty)
    return product


def _seed_stock(sku: str, qty: Decimal) -> None:
    from shopman.stockman import stock
    from shopman.stockman.models import Position, PositionKind

    position, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={
            "name": "Loja Principal",
            "kind": PositionKind.PHYSICAL,
            "is_saleable": True,
        },
    )
    stock.receive(
        quantity=qty,
        sku=sku,
        position=position,
        target_date=date.today(),
        reason="api storefront surface test seed stock",
    )
