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

from shopman.shop.models import Channel, Shop, Showcase


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
    Channel.objects.create(ref="web", name="Loja online", is_active=True, display_order=1)
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
PRODUCT_URL = "/api/v1/backstage/catalog/product/"
BULK_URL = "/api/v1/backstage/catalog/bulk/"
BULK_PRICE_URL = "/api/v1/backstage/catalog/bulk-price/"
REORDER_COLLECTIONS_URL = "/api/v1/backstage/catalog/reorder-collections/"
REORDER_ITEMS_URL = "/api/v1/backstage/catalog/reorder-items/"


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


def test_matrix_filtered_by_collection(client, operator, catalog):
    client.force_login(operator)
    resp = client.get(MATRIX_URL, {"collection": "doces"})
    assert resp.status_code == 200
    rows = resp.json()["matrix"]["rows"]
    assert [r["sku"] for r in rows] == ["BOLO"]  # só o membro de Doces
    # coleções (chips) permanecem completas, não filtradas
    assert {c["ref"] for c in resp.json()["matrix"]["collections"]} == {"doces"}


def test_matrix_filtered_by_smart_collection(client, operator, catalog):
    Collection.objects.create(
        ref="caros",
        name="Caros",
        is_active=True,
        rule={"match": "all", "conditions": [{"field": "base_price_q", "op": "gte", "value": 1000}]},
    )
    client.force_login(operator)
    resp = client.get(MATRIX_URL, {"collection": "caros"})
    assert resp.status_code == 200
    assert [r["sku"] for r in resp.json()["matrix"]["rows"]] == ["BOLO"]


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


# ── write: produto ("globalzinho") ─────────────────────────────────────────────


def test_product_pause_gates_every_surface(client, operator, catalog):
    """Pausar no nível produto derruba a disponibilidade em TODOS os canais."""
    client.force_login(operator)
    resp = client.post(
        PRODUCT_URL,
        data={"sku": "PAO", "is_sellable": False},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["is_sellable"] is False

    pao = Product.objects.get(sku="PAO")
    assert pao.is_sellable is False
    # As células (listing-level) ficam intactas; o gate é produto-level.
    for item in ListingItem.objects.filter(product__sku="PAO"):
        assert item.is_sellable is True
    # E a matriz reflete indisponível em toda superfície do produto.
    matrix = client.get(MATRIX_URL).json()["matrix"]
    pao_row = next(r for r in matrix["rows"] if r["sku"] == "PAO")
    assert pao_row["is_sellable"] is False
    assert all(not c["available"] for c in pao_row["cells"] if c["in_listing"])


def test_product_reactivate(client, operator, catalog):
    Product.objects.filter(sku="PAO").update(is_sellable=False)
    client.force_login(operator)
    resp = client.post(
        PRODUCT_URL,
        data={"sku": "PAO", "is_sellable": True},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert Product.objects.get(sku="PAO").is_sellable is True


def test_product_requires_field(client, operator, catalog):
    client.force_login(operator)
    resp = client.post(PRODUCT_URL, data={"sku": "PAO"}, content_type="application/json")
    assert resp.status_code == 400


def test_product_unknown_returns_400(client, operator, catalog):
    client.force_login(operator)
    resp = client.post(
        PRODUCT_URL,
        data={"sku": "NOPE", "is_sellable": False},
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_product_requires_manage_catalog(client, plain_staff, catalog):
    client.force_login(plain_staff)
    resp = client.post(
        PRODUCT_URL,
        data={"sku": "PAO", "is_sellable": False},
        content_type="application/json",
    )
    assert resp.status_code == 403


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


# ── write: preço em lote ───────────────────────────────────────────────────────


def test_bulk_price_set(client, operator, catalog):
    client.force_login(operator)
    resp = client.post(
        BULK_PRICE_URL,
        data={"surface_ref": "web", "skus": ["PAO", "BOLO"], "op": "set", "value": 999},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 2
    assert ListingItem.objects.get(listing__ref="web", product__sku="PAO").price_q == 999
    assert ListingItem.objects.get(listing__ref="web", product__sku="BOLO").price_q == 999


def test_bulk_price_pct_rounds(client, operator, catalog):
    client.force_login(operator)
    # PAO web = 600 → +10% = 660
    resp = client.post(
        BULK_PRICE_URL,
        data={"surface_ref": "web", "skus": ["PAO"], "op": "pct", "value": 10},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert ListingItem.objects.get(listing__ref="web", product__sku="PAO").price_q == 660


def test_bulk_price_delta_clamps_at_zero(client, operator, catalog):
    client.force_login(operator)
    # PAO web = 600; delta -1000 → clamp 0 (nunca negativo)
    resp = client.post(
        BULK_PRICE_URL,
        data={"surface_ref": "web", "skus": ["PAO"], "op": "delta", "value": -1000},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert ListingItem.objects.get(listing__ref="web", product__sku="PAO").price_q == 0


def test_bulk_price_by_collection(client, operator, catalog):
    client.force_login(operator)
    # BOLO web = 4800; coleção Doces só tem BOLO; +50% = 7200
    resp = client.post(
        BULK_PRICE_URL,
        data={"surface_ref": "web", "collection_ref": "doces", "op": "pct", "value": 50},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    assert ListingItem.objects.get(listing__ref="web", product__sku="BOLO").price_q == 7200
    # PAO (fora da coleção) intacto
    assert ListingItem.objects.get(listing__ref="web", product__sku="PAO").price_q == 600


def test_bulk_price_invalid_op(client, operator, catalog):
    client.force_login(operator)
    resp = client.post(
        BULK_PRICE_URL,
        data={"surface_ref": "web", "skus": ["PAO"], "op": "multiply", "value": 2},
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_bulk_price_set_negative_rejected(client, operator, catalog):
    client.force_login(operator)
    resp = client.post(
        BULK_PRICE_URL,
        data={"surface_ref": "web", "skus": ["PAO"], "op": "set", "value": -1},
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_bulk_all_channels_pause(client, operator, catalog):
    """surface_ref='*' aplica em todos os canais ativos."""
    client.force_login(operator)
    resp = client.post(
        BULK_URL,
        data={"surface_ref": "*", "skus": ["PAO"], "is_sellable": False},
        content_type="application/json",
    )
    assert resp.status_code == 200
    # PAO está em web + ifood → ambos pausados
    assert not ListingItem.objects.filter(product__sku="PAO", is_sellable=True).exists()


def test_bulk_price_all_channels(client, operator, catalog):
    client.force_login(operator)
    resp = client.post(
        BULK_PRICE_URL,
        data={"surface_ref": "*", "skus": ["PAO"], "op": "set", "value": 1234},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert ListingItem.objects.get(listing__ref="web", product__sku="PAO").price_q == 1234
    assert ListingItem.objects.get(listing__ref="ifood", product__sku="PAO").price_q == 1234


def test_bulk_price_requires_manage_catalog(client, plain_staff, catalog):
    client.force_login(plain_staff)
    resp = client.post(
        BULK_PRICE_URL,
        data={"surface_ref": "web", "skus": ["PAO"], "op": "set", "value": 100},
        content_type="application/json",
    )
    assert resp.status_code == 403


# ── reordenação ────────────────────────────────────────────────────────────────


def test_reorder_collections(client, operator, catalog):
    Collection.objects.create(ref="paes", name="Pães", is_active=True, sort_order=0)
    Collection.objects.filter(ref="doces").update(sort_order=9)
    client.force_login(operator)
    resp = client.post(
        REORDER_COLLECTIONS_URL,
        data={"ordered_refs": ["doces", "paes"]},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert Collection.objects.get(ref="doces").sort_order == 0
    assert Collection.objects.get(ref="paes").sort_order == 1


def test_reorder_items_manual(client, operator, catalog):
    coll = Collection.objects.get(ref="doces")
    CollectionItem.objects.create(
        collection=coll, product=Product.objects.get(sku="PAO"), sort_order=0
    )
    CollectionItem.objects.filter(collection=coll, product__sku="BOLO").update(sort_order=9)
    client.force_login(operator)
    resp = client.post(
        REORDER_ITEMS_URL,
        data={"collection_ref": "doces", "ordered_skus": ["BOLO", "PAO"]},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert CollectionItem.objects.get(collection=coll, product__sku="BOLO").sort_order == 0
    assert CollectionItem.objects.get(collection=coll, product__sku="PAO").sort_order == 1


# ── expositores como colunas (superfície display/feed, não-transacional) ────────


@pytest.fixture
def catalog_with_showcase(catalog):
    """Um Expositor menuboard exibindo a coleção Doces (só BOLO é membro)."""
    Showcase.objects.create(
        ref="tv-salao", name="TV do Salão", kind="menuboard", collections=["doces"], is_active=True
    )
    return catalog


def test_matrix_includes_showcase_column(client, operator, catalog_with_showcase):
    """O expositor entra como coluna à direita dos canais, marcada não-transacional."""
    client.force_login(operator)
    matrix = client.get(MATRIX_URL).json()["matrix"]
    surfaces = {s["ref"]: s for s in matrix["surfaces"]}
    assert [s["ref"] for s in matrix["surfaces"]] == ["web", "ifood", "tv-salao"]
    tv = surfaces["tv-salao"]
    assert tv["kind"] == "display"
    assert tv["transactional"] is False
    assert tv["is_active"] is True
    assert tv["output_path"] == "/menuboard/tv-salao/"


def test_showcase_cell_membership_and_no_price(client, operator, catalog_with_showcase):
    """Célula de expositor: membro (via coleção) disponível, sem preço; não-membro N/A."""
    client.force_login(operator)
    matrix = client.get(MATRIX_URL).json()["matrix"]
    rows = {r["sku"]: r for r in matrix["rows"]}

    bolo_tv = next(c for c in rows["BOLO"]["cells"] if c["surface_ref"] == "tv-salao")
    assert bolo_tv["in_listing"] is True  # BOLO está em Doces → no expositor
    assert bolo_tv["available"] is True
    assert bolo_tv["price_q"] is None  # expositor não transaciona

    pao_tv = next(c for c in rows["PAO"]["cells"] if c["surface_ref"] == "tv-salao")
    assert pao_tv["in_listing"] is False  # PAO não está em Doces → fora deste expositor


def test_showcase_cell_pause_routes_to_showcase(client, operator, catalog_with_showcase):
    """Pausar a célula do expositor grava em Showcase.options[paused_skus] (sem tocar listings)."""
    client.force_login(operator)
    resp = client.post(
        CELL_URL,
        data={"sku": "BOLO", "surface_ref": "tv-salao", "is_sellable": False},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["is_sellable"] is False
    assert Showcase.objects.get(ref="tv-salao").paused_skus() == {"BOLO"}

    # e a matriz reflete indisponível só nesta coluna
    matrix = client.get(MATRIX_URL).json()["matrix"]
    bolo_tv = next(
        c for r in matrix["rows"] if r["sku"] == "BOLO" for c in r["cells"] if c["surface_ref"] == "tv-salao"
    )
    assert bolo_tv["available"] is False

    # reativar remove da lista
    resp = client.post(
        CELL_URL,
        data={"sku": "BOLO", "surface_ref": "tv-salao", "is_sellable": True},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert Showcase.objects.get(ref="tv-salao").paused_skus() == set()


def test_showcase_cell_price_rejected(client, operator, catalog_with_showcase):
    """Expositor não aceita preço/publicação — só pausar/reativar."""
    client.force_login(operator)
    resp = client.post(
        CELL_URL,
        data={"sku": "BOLO", "surface_ref": "tv-salao", "price_q": 100},
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_global_pause_gates_showcase_column(client, operator, catalog_with_showcase):
    """A pausa global do produto atinge o expositor (cada um é um)."""
    client.force_login(operator)
    client.post(PRODUCT_URL, data={"sku": "BOLO", "is_sellable": False}, content_type="application/json")
    matrix = client.get(MATRIX_URL).json()["matrix"]
    bolo_tv = next(
        c for r in matrix["rows"] if r["sku"] == "BOLO" for c in r["cells"] if c["surface_ref"] == "tv-salao"
    )
    assert bolo_tv["available"] is False  # global gateia o expositor mesmo sem pausa local


def test_showcase_bulk_pause(client, operator, catalog_with_showcase):
    """Bulk numa coluna de expositor pausa os itens (options[paused_skus])."""
    client.force_login(operator)
    resp = client.post(
        BULK_URL,
        data={"surface_ref": "tv-salao", "skus": ["BOLO"], "is_sellable": False},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    assert Showcase.objects.get(ref="tv-salao").paused_skus() == {"BOLO"}


def test_reorder_items_smart_rejected(client, operator, catalog):
    Collection.objects.create(
        ref="caros",
        name="Caros",
        is_active=True,
        rule={"match": "all", "conditions": [{"field": "base_price_q", "op": "gte", "value": 1000}]},
    )
    client.force_login(operator)
    resp = client.post(
        REORDER_ITEMS_URL,
        data={"collection_ref": "caros", "ordered_skus": ["BOLO"]},
        content_type="application/json",
    )
    assert resp.status_code == 400  # coleção por regra não tem ordem manual


# ── Arc C: sync-status + resync ───────────────────────────────────────────────

SYNC_STATUS_URL = "/api/v1/backstage/catalog/sync-status/"
RESYNC_URL = "/api/v1/backstage/catalog/resync/"


def test_sync_status_requires_manage_catalog(client, plain_staff, catalog):
    client.force_login(plain_staff)
    assert client.get(SYNC_STATUS_URL).status_code == 403


def test_sync_status_returns_recorded_states(client, operator, catalog):
    from shopman.shop.services import catalog_sync

    catalog_sync.record_sync("PAO", "meta", status="synced", external_id="PAO")
    catalog_sync.record_sync("PAO", "google", status="error", error="boom")

    client.force_login(operator)
    resp = client.get(SYNC_STATUS_URL)
    assert resp.status_code == 200
    data = resp.json()["sync_status"]
    assert data["PAO"]["meta"]["status"] == "synced"
    assert data["PAO"]["meta"]["last_synced_at"]
    assert data["PAO"]["google"]["status"] == "error"
    assert data["PAO"]["google"]["error"] == "boom"


def test_sync_status_filtered_by_platform(client, operator, catalog):
    from shopman.shop.services import catalog_sync

    catalog_sync.record_sync("PAO", "meta", status="synced")
    catalog_sync.record_sync("PAO", "google", status="synced")

    client.force_login(operator)
    data = client.get(SYNC_STATUS_URL, {"platform": "meta"}).json()["sync_status"]
    assert set(data["PAO"]) == {"meta"}


def test_resync_requires_sku(client, operator, catalog):
    client.force_login(operator)
    resp = client.post(RESYNC_URL, data={}, content_type="application/json")
    assert resp.status_code == 400


def test_resync_enqueues_directive(client, operator, catalog):
    from shopman.orderman.models import Directive

    from shopman.shop.directives import CATALOG_PROJECT_SKU

    client.force_login(operator)
    resp = client.post(
        RESYNC_URL,
        data={"sku": "PAO", "platform": "ifood"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["platforms"] == ["ifood"]
    assert Directive.objects.filter(topic=CATALOG_PROJECT_SKU, payload__sku="PAO").exists()
