"""Menuboard — Expositor (Showcase) de tipo menuboard, público e em tempo real."""

from __future__ import annotations

import pytest
from shopman.offerman.models import Collection, CollectionItem, Product

from shopman.shop.models import Showcase
from shopman.shop.projections.menuboard import MenuboardError, build_menuboard


@pytest.fixture
def menuboard(db):
    Showcase.objects.create(
        ref="tv-balcao", name="Quadro do Balcão", kind="menuboard", collections=["paes", "doces"]
    )
    paes = Collection.objects.create(ref="paes", name="Pães", is_active=True, sort_order=1)
    doces = Collection.objects.create(ref="doces", name="Doces", is_active=True, sort_order=2)
    pao = Product.objects.create(
        sku="PAO", name="Pão na Chapa", unit="un", base_price_q=800,
        is_published=True, is_sellable=True, short_description="Na manteiga",
    )
    bolo = Product.objects.create(
        sku="BOLO", name="Bolo", unit="un", base_price_q=1200, is_published=True, is_sellable=True,
    )
    CollectionItem.objects.create(collection=paes, product=pao)
    CollectionItem.objects.create(collection=doces, product=bolo)
    return {"pao": pao, "bolo": bolo}


def test_sections_are_showcase_collections(menuboard):
    board = build_menuboard("tv-balcao")
    assert board.title == "Quadro do Balcão"
    assert [g.title for g in board.groups] == ["Pães", "Doces"]  # ordem do expositor
    assert board.available_count == 2
    pao = next(i for g in board.groups for i in g.items if i.sku == "PAO")
    assert pao.price_q == 800 and pao.available is True and pao.description == "Na manteiga"


def test_paused_product_drops_from_available(menuboard):
    menuboard["pao"].is_sellable = False
    menuboard["pao"].save()
    board = build_menuboard("tv-balcao")
    pao = next(i for g in board.groups for i in g.items if i.sku == "PAO")
    assert pao.available is False
    assert board.available_count == 1  # só o bolo


def test_smart_collection_section(db):
    Showcase.objects.create(ref="tv", name="TV", kind="menuboard", collections=["caros"])
    Collection.objects.create(
        ref="caros", name="Caros", is_active=True,
        rule={"match": "all", "conditions": [{"field": "base_price_q", "op": "gte", "value": 1000}]},
    )
    Product.objects.create(sku="BOLO", name="Bolo", base_price_q=4500, is_published=True, is_sellable=True)
    Product.objects.create(sku="PAO", name="Pão", base_price_q=500, is_published=True, is_sellable=True)
    board = build_menuboard("tv")
    assert [i.sku for g in board.groups for i in g.items] == ["BOLO"]  # regra resolve a seção


def test_rejects_feed_showcase(db):
    Showcase.objects.create(ref="google", name="G", kind="google", collections=["x"])
    with pytest.raises(MenuboardError):
        build_menuboard("google")


def test_rejects_missing(db):
    with pytest.raises(MenuboardError):
        build_menuboard("fantasma")


# ── views públicas ──────────────────────────────────────────────────────────────


def test_page_public_200(client, menuboard):
    resp = client.get("/menuboard/tv-balcao/")
    assert resp.status_code == 200
    assert "Quadro do Balcão".encode() in resp.content
    assert b"menuboard()" in resp.content


def test_data_public_json(client, menuboard):
    resp = client.get("/menuboard/tv-balcao/data/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ref"] == "tv-balcao"
    assert body["available_count"] == 2
    assert [g["title"] for g in body["groups"]] == ["Pães", "Doces"]


def test_page_404_for_unknown(client, db):
    assert client.get("/menuboard/fantasma/").status_code == 404
    assert client.get("/menuboard/fantasma/data/").status_code == 404
