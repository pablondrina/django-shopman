"""Cupom restrito a grupo/segmento só vale para quem é elegível.

Regressão do audit pré-staging: o cupom FUNCIONARIO (``customer_segments=["staff"]``)
era aceito por qualquer cliente. O modifier não casa o segmento, então o desconto
saía 0 e o cupom "grudava" no carrinho sem aviso. Agora ``apply_coupon`` recusa no
gate (``coupon_not_eligible``) quem não pertence ao grupo/segmento alvo.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone
from shopman.guestman.models import Customer, CustomerGroup
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.shop.models import Channel, Shop
from shopman.storefront.models import Coupon, Promotion

pytestmark = pytest.mark.django_db


@pytest.fixture
def funcionario_coupon(db):
    Shop.objects.create(name="Test Shop")
    Channel.objects.create(ref="web", name="Web")
    product = Product.objects.create(
        sku="PAO-CUPOM", name="Pão", base_price_q=2500, is_published=True, is_sellable=True
    )
    listing = Listing.objects.create(ref="web", name="Web", is_active=True, priority=10)
    ListingItem.objects.create(
        listing=listing, product=product, price_q=2500, is_published=True, is_sellable=True
    )
    _seed_stock(product.sku)
    now = timezone.now()
    promo = Promotion.objects.create(
        name="Desconto Funcionário",
        type=Promotion.PERCENT,
        value=20,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
        customer_segments=["staff"],
    )
    return Coupon.objects.create(code="FUNCIONARIO", promotion=promo, max_uses=0)


def _seed_stock(sku: str) -> None:
    from shopman.stockman import stock
    from shopman.stockman.models import Position, PositionKind

    position, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    stock.receive(quantity=Decimal("100"), sku=sku, position=position, target_date=date.today(), reason="seed")


def _login_as_customer(client: Client, customer: Customer):
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    info = AuthCustomerInfo(
        uuid=customer.uuid, name=customer.name, phone=customer.phone,
        email=getattr(customer, "email", None) or None, is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")


def _fill_cart(client: Client) -> None:
    client.put(
        "/api/v1/cart/skus/PAO-CUPOM/",
        data=json.dumps({"qty": 1}),
        content_type="application/json",
    )


def _apply(client: Client) -> Client:
    return client.post(
        "/api/v1/cart/coupon/",
        data=json.dumps({"code": "FUNCIONARIO"}),
        content_type="application/json",
    )


def test_anonymous_customer_cannot_apply_staff_coupon(client: Client, funcionario_coupon):
    _fill_cart(client)
    resp = _apply(client)
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "coupon_not_eligible"
    assert "conta" in body["detail"].lower()


def test_non_staff_customer_cannot_apply_staff_coupon(client: Client, funcionario_coupon):
    varejo = CustomerGroup.objects.create(ref="varejo", name="Varejo")
    customer = Customer.objects.create(
        ref="CUS-VAREJO-01", first_name="Cliente", phone="+5543988887777", group=varejo
    )
    _login_as_customer(client, customer)
    _fill_cart(client)
    resp = _apply(client)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "coupon_not_eligible"


def test_staff_customer_can_apply_staff_coupon(client: Client, funcionario_coupon):
    staff = CustomerGroup.objects.create(ref="staff", name="Equipe")
    customer = Customer.objects.create(
        ref="CUS-STAFF-01", first_name="Funcionário", phone="+5543988886666", group=staff
    )
    _login_as_customer(client, customer)
    _fill_cart(client)
    resp = _apply(client)
    assert resp.status_code == 200
    assert "cart" in resp.json()
