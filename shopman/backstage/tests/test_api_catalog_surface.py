"""Headless catalog matrix API contract (api/v1/backstage/catalog/*).

The catalog hub surface the Gestor consumes: read the produto × superfície matrix
and mutate cells (pause/publish/price) + bulk scoped to surface/collection/skus.
Gate: ``shop.manage_catalog`` (staff operator). Staff without it — and non-staff —
are blocked.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from shopman.offerman.models import (
    Collection,
    CollectionItem,
    Listing,
    ListingItem,
    Product,
)

from shopman.shop.models import Channel, Shop


def _manage_catalog_perm() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"),
        codename="manage_catalog",
    )


@pytest.fixture
def shop(db):
    return Shop.objects.create(name="Loja")


@pytest.fixture
def operator(db, shop):
    user = User.objects.create_user("catalog-api", password="pw", is_staff=True)
    user.user_permissions.add(_manage_catalog_perm())
    return user


@pytest.fixture
def plain_staff(db, shop):
    return User.objects.create_user("plain-staff", password="pw", is_staff=True)


@pytest.fixture
def catalog(db):
    """Duas superfícies (web, ifood), dois produtos, células e uma coleção."""
    Channel.objects.create(ref="web", name="E-commerce", is_active=True, display_order=1)
    Channel.objects.create(ref="ifood", name="iFood", is_active=True, display_order=2)
    web = Listing.objects.create(ref="web", name="Web", is_active=True)
    ifood = Listing.objects.create(ref="ifood", name="iFood", is_active=True)

    pao = Product.objects.create(
        sku="PAO", name="Pão", unit="un", base_price_q=500, is_published=True, is_sellable=True
    )
    pao.keywords.add("padaria")
    bolo = Product.objects.create(
        sku="BOLO", name="Bolo", unit="un", base_price_q=4500, is_published=True, is_sellable=True
    )

    coll = Collection.objects.create(ref="doces", name="Doces", is_active=True)
    CollectionItem.objects.create(collection=coll, product=bolo, is_primary=True)

    ListingItem.objects.create(listing=web, product=pao, price_q=600)
    ListingItem.objects.create(listing=web, product=bolo, price_q=4800)
    ListingItem.objects.create(listing=ifood, product=pao, price_q=650)
    return {"pao": pao, "bolo": bolo, "coll": coll}


MATRIX_URL = "/api/v1/backstage/catalog/"
CELL_URL = "/api/v1/backstage/catalog/cell/"
BULK_URL = "/api/v1/backstage/catalog/bulk/"


# ── gate ────────────────────────────────────────────────────────────────────


def test_matrix_requires_manage_catalog(client, plain_staff, catalog):
    client.force_login(plain_staff)
    assert client.get(MATRIX_URL).status_code == 403


def test_matrix_blocks_anonymous(client, catalog):
    assert client.get(MATRIX_URL).status_code in (401, 403)


# ── read ────────────────────────────────────────────────────────────────────


def test_matrix_shape(client, operator, catalog):
    client.force_login(operator)
    resp = client.get(MATRIX_URL)
    assert resp.status_code == 200
    matrix = resp.json()["matrix"]

    refs = [s["ref"] for s in matrix["surfaces"]]
    assert refs == ["web", "ifood"]  # por display_order
    assert all(s["capability"] == "transactional" for s in matrix["surfaces"])

    rows = {r["sku"]: r for r in matrix["rows"]}
    assert set(rows) == {"PAO", "BOLO"}

    # PAO está nas duas superfícies; BOLO só na web.
    pao_cells = {c["surface_ref"]: c for c in rows["PAO"]["cells"]}
    assert pao_cells["web"]["in_listing"] is True
    assert pao_cells["web"]["price_q"] == 600
    assert pao_cells["ifood"]["in_listing"] is True
    bolo_cells = {c["surface_ref"]: c for c in rows["BOLO"]["cells"]}
    assert bolo_cells["web"]["in_listing"] is True
    assert bolo_cells["ifood"]["in_listing"] is False

    colls = {c["ref"]: c for c in matrix["collections"]}
    assert colls["doces"]["product_count"] == 1


# ── write: célula ─────────────────────────────────────────────────────────────


def test_cell_pause(client, operator, catalog):
    client.force_login(operator)
    resp = client.post(
        CELL_URL,
        data={"sku": "PAO", "surface_ref": "web", "is_sellable": False},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["is_sellable"] is False
    item = ListingItem.objects.get(listing__ref="web", product__sku="PAO")
    assert item.is_sellable is False


def test_cell_price(client, operator, catalog):
    client.force_login(operator)
    resp = client.post(
        CELL_URL,
        data={"sku": "PAO", "surface_ref": "web", "price_q": 720},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert ListingItem.objects.get(listing__ref="web", product__sku="PAO").price_q == 720


def test_cell_unknown_returns_400(client, operator, catalog):
    client.force_login(operator)
    resp = client.post(
        CELL_URL,
        data={"sku": "BOLO", "surface_ref": "ifood", "is_sellable": False},
        content_type="application/json",
    )
    assert resp.status_code == 400  # BOLO não está na superfície ifood


def test_cell_negative_price_rejected(client, operator, catalog):
    client.force_login(operator)
    resp = client.post(
        CELL_URL,
        data={"sku": "PAO", "surface_ref": "web", "price_q": -1},
        content_type="application/json",
    )
    assert resp.status_code == 400


# ── write: bulk ───────────────────────────────────────────────────────────────


def test_bulk_by_skus(client, operator, catalog):
    client.force_login(operator)
    resp = client.post(
        BULK_URL,
        data={"surface_ref": "web", "skus": ["PAO", "BOLO"], "is_sellable": False},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 2
    assert not ListingItem.objects.filter(listing__ref="web", is_sellable=True).exists()


def test_bulk_by_collection(client, operator, catalog):
    client.force_login(operator)
    resp = client.post(
        BULK_URL,
        data={"surface_ref": "web", "collection_ref": "doces", "is_published": False},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 1  # só BOLO está em Doces
    assert ListingItem.objects.get(listing__ref="web", product__sku="BOLO").is_published is False
    # PAO (fora da coleção) intacto
    assert ListingItem.objects.get(listing__ref="web", product__sku="PAO").is_published is True


def test_bulk_by_smart_collection(client, operator, catalog):
    """Bulk scoped a uma coleção SMART resolve por regra."""
    Collection.objects.create(
        ref="caros",
        name="Caros",
        is_active=True,
        rule={"match": "all", "conditions": [{"field": "base_price_q", "op": "gte", "value": 1000}]},
    )
    client.force_login(operator)
    resp = client.post(
        BULK_URL,
        data={"surface_ref": "web", "collection_ref": "caros", "is_sellable": False},
        content_type="application/json",
    )
    assert resp.status_code == 200
    # só BOLO (4500) >= 1000; PAO (500) não
    assert resp.json()["count"] == 1
    assert ListingItem.objects.get(listing__ref="web", product__sku="BOLO").is_sellable is False


def test_bulk_requires_field(client, operator, catalog):
    client.force_login(operator)
    resp = client.post(
        BULK_URL,
        data={"surface_ref": "web", "skus": ["PAO"]},
        content_type="application/json",
    )
    assert resp.status_code == 400  # nem is_published nem is_sellable
