from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client as DjangoClient
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


def test_api_storefront_menu_sets_csrf_cookie(client):
    _seed_surface()

    resp = client.get("/api/v1/storefront/menu/")

    assert resp.status_code == 200
    assert "csrftoken" in resp.cookies


def test_api_storefront_checkout_returns_projection_contract(client):
    _seed_surface()

    resp = client.get("/api/v1/storefront/checkout/")

    assert resp.status_code == 200
    data = resp.json()["checkout"]
    assert data["cart"]["is_empty"] is True
    assert data["has_pickup"] is True
    assert data["has_delivery"] is True
    assert data["default_payment_method"]
    assert data["support_whatsapp_url"].startswith("https://wa.me/")
    assert isinstance(data["payment_methods"], list)
    assert isinstance(data["pickup_slots"], list)
    if data["pickup_slots"]:
        slot = data["pickup_slots"][0]
        assert {"ref", "label", "starts_at", "enabled", "reason", "is_earliest"}.issubset(slot)
    assert "csrftoken" in resp.cookies


def test_api_cart_sku_qty_accepts_authenticated_session_with_csrf_header():
    product = _seed_surface(stock_qty=Decimal("10"))
    user = get_user_model().objects.create_user(username="staff", password="secret")
    client = DjangoClient(enforce_csrf_checks=True)
    client.force_login(user)

    menu = client.get("/api/v1/storefront/menu/")
    token = menu.cookies["csrftoken"].value
    add = client.put(
        f"/api/v1/cart/skus/{product.sku}/",
        data=json.dumps({"qty": 1}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )

    assert add.status_code == 200
    assert add.json()["cart"]["items_count"] == 1


def test_api_cart_sku_qty_requires_origin_or_referer_for_secure_authenticated_session():
    product = _seed_surface(stock_qty=Decimal("10"))
    user = get_user_model().objects.create_user(username="secure-staff", password="secret")
    client = DjangoClient(enforce_csrf_checks=True)
    client.force_login(user)

    menu = client.get("/api/v1/storefront/menu/", secure=True)
    token = menu.cookies["csrftoken"].value
    missing_referer = client.put(
        f"/api/v1/cart/skus/{product.sku}/",
        data=json.dumps({"qty": 1}),
        content_type="application/json",
        secure=True,
        HTTP_X_CSRFTOKEN=token,
    )

    assert missing_referer.status_code == 403

    with_origin = client.put(
        f"/api/v1/cart/skus/{product.sku}/",
        data=json.dumps({"qty": 1}),
        content_type="application/json",
        secure=True,
        HTTP_X_CSRFTOKEN=token,
        HTTP_ORIGIN="https://testserver",
    )

    assert with_origin.status_code == 200


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


def test_api_cart_sku_qty_stock_error_returns_rich_payload(client):
    from shopman.shop.services.cart import CartUnavailableError

    product = _seed_surface(stock_qty=Decimal("10"))
    stock_error = CartUnavailableError(
        sku=product.sku,
        requested_qty=5,
        available_qty=2,
        error_code="below_stock",
        is_paused=False,
        substitutes=[{"sku": "ALT-PAO", "name": "Pão alternativo", "reason": "Mais estoque"}],
    )

    with patch("shopman.storefront.services.cart_mutations.CartService.add_item", side_effect=stock_error):
        response = client.put(
            f"/api/v1/cart/skus/{product.sku}/",
            data=json.dumps({"qty": 5}),
            content_type="application/json",
        )

    assert response.status_code == 409
    data = response.json()
    assert data["title"] == "Revise este item"
    assert data["name"] == product.name
    assert data["items"] == [
        {
            "sku": product.sku,
            "name": product.name,
            "requested_qty": 5,
            "available_qty": 2,
            "reason": "Estoque disponível agora: 2 unidade(s).",
        }
    ]
    assert data["substitutes"][0]["name"] == "Pão alternativo"


def _seed_surface(*, stock_qty: Decimal | None = None) -> Product:
    Shop.objects.create(
        name="Demo Bakery",
        brand_name="Demo Bakery",
        short_name="Demo",
        phone="554333231997",
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
