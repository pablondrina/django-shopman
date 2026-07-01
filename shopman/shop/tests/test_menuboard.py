"""Menuboard — superfície display pública alimentada por coleção, tempo real."""

from __future__ import annotations

import pytest
from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product

from shopman.shop.models import Channel
from shopman.shop.projections.menuboard import MenuboardError, build_menuboard


@pytest.fixture
def menuboard(db):
    Channel.objects.create(
        ref="tv-balcao",
        name="Quadro do Balcão",
        is_active=True,
        config={"capability": "display", "content": {"source": "collection", "collection": "cafe"}},
    )
    Listing.objects.create(ref="tv-balcao", name="TV Balcão", is_active=True)
    cafe = Collection.objects.create(ref="cafe", name="Café da Manhã", is_active=True)
    paes = Collection.objects.create(ref="paes", name="Pães", is_active=True)

    pao = Product.objects.create(
        sku="PAO", name="Pão na Chapa", unit="un", base_price_q=800, is_published=True, is_sellable=True,
        short_description="Na manteiga",
    )
    cafe_prod = Product.objects.create(
        sku="CAFE", name="Café Coado", unit="un", base_price_q=500, is_published=True, is_sellable=True,
    )
    CollectionItem.objects.create(collection=cafe, product=pao)
    CollectionItem.objects.create(collection=cafe, product=cafe_prod)
    CollectionItem.objects.create(collection=paes, product=pao, is_primary=True)
    return {"pao": pao, "cafe": cafe_prod}


# ── projection ────────────────────────────────────────────────────────────────


def test_build_groups_and_prices(menuboard):
    board = build_menuboard("tv-balcao")
    assert board.title == "Quadro do Balcão"
    assert board.subtitle == "Café da Manhã"
    assert board.available_count == 2
    # Pão agrupado sob a coleção primária "Pães"; café sob a fonte "Café da Manhã".
    sections = {g.title: [i.name for i in g.items] for g in board.groups}
    assert "Pães" in sections and "Pão na Chapa" in sections["Pães"]
    pao_item = next(i for g in board.groups for i in g.items if i.sku == "PAO")
    assert pao_item.price_q == 800
    assert pao_item.available is True
    assert pao_item.description == "Na manteiga"


def test_listing_override_price_and_pause(menuboard):
    # override de preço e pausa na superfície (via ListingItem)
    ListingItem.objects.create(
        listing=Listing.objects.get(ref="tv-balcao"),
        product=menuboard["pao"],
        price_q=950,
        is_sellable=False,
    )
    board = build_menuboard("tv-balcao")
    pao_item = next(i for g in board.groups for i in g.items if i.sku == "PAO")
    assert pao_item.price_q == 950  # preço da superfície
    assert pao_item.available is False  # pausado nesta superfície
    assert board.available_count == 1  # só o café


def test_rejects_non_display_surface(db):
    Channel.objects.create(ref="web", name="Web", is_active=True)  # capability default = transactional
    with pytest.raises(MenuboardError):
        build_menuboard("web")


def test_rejects_display_without_collection(db):
    Channel.objects.create(
        ref="tv-x", name="TV", is_active=True, config={"capability": "display"}
    )
    with pytest.raises(MenuboardError):
        build_menuboard("tv-x")


# ── views (públicas, sem auth — uma TV só abre a URL) ───────────────────────────


def test_page_public_200(client, menuboard):
    resp = client.get("/menuboard/tv-balcao/")
    assert resp.status_code == 200
    assert "Quadro do Balcão".encode() in resp.content  # título embutido p/ paint imediato
    assert b"menuboard()" in resp.content  # componente Alpine


def test_data_public_json(client, menuboard):
    resp = client.get("/menuboard/tv-balcao/data/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["surface_ref"] == "tv-balcao"
    assert body["available_count"] == 2
    assert any(g["title"] == "Pães" for g in body["groups"])


def test_page_404_for_non_display(client, db):
    Channel.objects.create(ref="web", name="Web", is_active=True)
    assert client.get("/menuboard/web/").status_code == 404
    assert client.get("/menuboard/web/data/").status_code == 404
