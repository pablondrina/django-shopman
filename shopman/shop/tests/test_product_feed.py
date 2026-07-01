"""Product feed — Expositor (Showcase) de feed (Google/Meta), RSS 2.0 público."""

from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest
from shopman.offerman.models import Collection, CollectionItem, Product

from shopman.shop.models import Shop, Showcase

G = "{http://base.google.com/ns/1.0}"


@pytest.fixture
def feed(db):
    Shop.objects.create(name="Nelson Boulangerie")
    Showcase.objects.create(ref="google", name="Google Shopping", kind="google", collections=["vitrine"])
    Showcase.objects.create(ref="meta", name="Meta", kind="meta", collections=["vitrine"])
    vitrine = Collection.objects.create(ref="vitrine", name="Vitrine", is_active=True)
    com_foto = Product.objects.create(
        sku="BAGUETE", name="Baguete", unit="un", base_price_q=1300,
        is_published=True, is_sellable=True, image_url="https://cdn.test/baguete.jpg",
        long_description="Pão de tradição francesa",
    )
    sem_foto = Product.objects.create(
        sku="SEMFOTO", name="Sem Foto", unit="un", base_price_q=500, is_published=True, is_sellable=True,
    )
    CollectionItem.objects.create(collection=vitrine, product=com_foto)
    CollectionItem.objects.create(collection=vitrine, product=sem_foto)
    return {"com_foto": com_foto}


def _items(xml: bytes):
    return ET.fromstring(xml).find("channel").findall("item")


def test_feed_is_valid_google_rss(client, feed):
    resp = client.get("/feed/google.xml")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("application/xml")
    items = _items(resp.content)
    assert len(items) == 1  # só o produto COM imagem
    item = items[0]
    assert item.find(f"{G}id").text == "BAGUETE"
    assert item.find(f"{G}price").text == "13.00 BRL"
    assert item.find(f"{G}availability").text == "in_stock"  # google = underscore
    assert item.find(f"{G}brand").text == "Nelson Boulangerie"
    assert item.find(f"{G}identifier_exists").text == "no"
    assert item.find(f"{G}custom_label_0").text == "vitrine"  # coleção do expositor
    assert item.find(f"{G}product_type").text == "Vitrine"


def test_meta_kind_uses_spaced_availability(client, feed):
    item = _items(client.get("/feed/meta.xml").content)[0]
    assert item.find(f"{G}availability").text == "in stock"  # meta = espaço (verificado)


def test_paused_is_out_of_stock(client, feed):
    feed["com_foto"].is_sellable = False
    feed["com_foto"].save()
    item = _items(client.get("/feed/google.xml").content)[0]
    assert item.find(f"{G}availability").text == "out_of_stock"


def test_smart_collection_feed(client, db):
    Showcase.objects.create(ref="caros", name="Caros", kind="google", collections=["regra"])
    Collection.objects.create(
        ref="regra", name="Regra", is_active=True,
        rule={"match": "all", "conditions": [{"field": "base_price_q", "op": "gte", "value": 1000}]},
    )
    Product.objects.create(sku="BOLO", name="Bolo", base_price_q=4500, is_published=True, is_sellable=True, image_url="https://cdn.test/bolo.jpg")
    Product.objects.create(sku="PAO", name="Pão", base_price_q=500, is_published=True, is_sellable=True, image_url="https://cdn.test/pao.jpg")
    assert [i.find(f"{G}id").text for i in _items(client.get("/feed/caros.xml").content)] == ["BOLO"]


def test_menuboard_is_not_a_feed(client, db):
    Showcase.objects.create(ref="tv", name="TV", kind="menuboard", collections=["x"])
    assert client.get("/feed/tv.xml").status_code == 404


def test_unknown_404(client, db):
    assert client.get("/feed/fantasma.xml").status_code == 404
