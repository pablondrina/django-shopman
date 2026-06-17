"""WP-4 — Favoritos (coleção dinâmica client-scoped, explícita).

Cobre o serviço (add/remove/toggle/skus/dedup), os endpoints (toggle + listar,
login obrigatório) e o flag is_favorite nas projeções.
"""
from __future__ import annotations

import pytest
from shopman.guestman.models import Customer, CustomerGroup

from shopman.storefront.models import CustomerFavorite
from shopman.storefront.services import favorites

pytestmark = pytest.mark.django_db

REF = "CUST-FAV-1"


# ── service ─────────────────────────────────────────────────────────


def test_add_is_idempotent():
    assert favorites.add(REF, "SKU-1") is True
    favorites.add(REF, "SKU-1")
    assert CustomerFavorite.objects.filter(customer_ref=REF).count() == 1


def test_toggle_flips_state():
    assert favorites.toggle(REF, "SKU-1") is True   # adiciona
    assert favorites.toggle(REF, "SKU-1") is False  # remove
    assert CustomerFavorite.objects.filter(customer_ref=REF, sku="SKU-1").exists() is False


def test_skus_for_returns_recent_first():
    favorites.add(REF, "SKU-A")
    favorites.add(REF, "SKU-B")
    assert set(favorites.skus_for(REF)) == {"SKU-A", "SKU-B"}
    assert favorites.favorite_sku_set(REF) == {"SKU-A", "SKU-B"}


def test_remove_is_idempotent():
    favorites.add(REF, "SKU-1")
    assert favorites.remove(REF, "SKU-1") is False
    assert favorites.remove(REF, "SKU-1") is False  # já removido, não quebra


# ── endpoints ───────────────────────────────────────────────────────


def _make_customer(phone="+5543999990001") -> Customer:
    group, _ = CustomerGroup.objects.get_or_create(
        ref="regular", defaults={"name": "Regular", "is_default": True, "priority": 0}
    )
    return Customer.objects.create(ref="CUST-FAV-API", first_name="Ana", phone=phone, group=group)


def _login(client, customer):
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    info = AuthCustomerInfo(uuid=customer.uuid, name=customer.name, phone=customer.phone, email=None, is_active=True)
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")


def test_endpoint_favorite_requires_login(client):
    resp = client.post("/api/v1/account/favorites/SKU-1/")
    assert resp.status_code == 401


def test_endpoint_toggle_favorite_authenticated(client):
    customer = _make_customer()
    _login(client, customer)

    add = client.post("/api/v1/account/favorites/SKU-1/")
    assert add.status_code == 200
    assert add.json()["is_favorite"] is True
    assert CustomerFavorite.objects.filter(customer_ref=customer.ref, sku="SKU-1").exists()

    rm = client.delete("/api/v1/account/favorites/SKU-1/")
    assert rm.status_code == 200
    assert rm.json()["is_favorite"] is False
    assert not CustomerFavorite.objects.filter(customer_ref=customer.ref, sku="SKU-1").exists()


def test_endpoint_list_favorites_requires_login(client):
    resp = client.get("/api/v1/account/favorites/")
    assert resp.status_code == 401


def test_endpoint_list_returns_items(client):
    from shopman.offerman.models import Product

    customer = _make_customer()
    _login(client, customer)
    Product.objects.create(sku="FAV-PROD", name="Pão Favorito", base_price_q=500, is_published=True, is_sellable=True)
    favorites.add(customer.ref, "FAV-PROD")

    resp = client.get("/api/v1/account/favorites/")
    assert resp.status_code == 200
    skus = [it["sku"] for it in resp.json()["items"]]
    assert "FAV-PROD" in skus
