"""Product feed — superfície FEED (Google Merchant / Meta) alimentada por coleção.

Feed RSS 2.0 público, formato Google-compatível (verificado). Meta aceita o mesmo
XML. Pull: o parceiro agenda o fetch da URL — sem credenciais.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest
from shopman.offerman.models import Collection, CollectionItem, Product

from shopman.shop.models import Channel, Shop

G = "{http://base.google.com/ns/1.0}"


@pytest.fixture
def feed_surface(db):
    Shop.objects.create(name="Nelson Boulangerie")
    Channel.objects.create(
        ref="google",
        name="Google Shopping",
        is_active=True,
        config={"capability": "feed", "content": {"source": "collection", "collection": "vitrine"}},
    )
    vitrine = Collection.objects.create(ref="vitrine", name="Vitrine", is_active=True)
    paes = Collection.objects.create(ref="paes", name="Pães", is_active=True)
    com_foto = Product.objects.create(
        sku="BAGUETE", name="Baguete", unit="un", base_price_q=1300,
        is_published=True, is_sellable=True, image_url="https://cdn.test/baguete.jpg",
        long_description="Pão de tradição francesa",
    )
    sem_foto = Product.objects.create(
        sku="SEMFOTO", name="Sem Foto", unit="un", base_price_q=500,
        is_published=True, is_sellable=True,
    )
    CollectionItem.objects.create(collection=vitrine, product=com_foto)
    CollectionItem.objects.create(collection=vitrine, product=sem_foto)
    CollectionItem.objects.create(collection=paes, product=com_foto, is_primary=True)
    return {"com_foto": com_foto, "sem_foto": sem_foto}


def _items(xml: bytes):
    root = ET.fromstring(xml)
    return root.find("channel").findall("item")


def test_feed_is_valid_google_rss(client, feed_surface):
    resp = client.get("/feed/google.xml")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("application/xml")
    items = _items(resp.content)
    # só o produto COM imagem entra (image_link é obrigatório)
    assert len(items) == 1
    item = items[0]
    assert item.find(f"{G}id").text == "BAGUETE"
    assert item.find(f"{G}title").text == "Baguete"
    assert item.find(f"{G}price").text == "13.00 BRL"
    assert item.find(f"{G}availability").text == "in_stock"
    assert item.find(f"{G}condition").text == "new"
    assert item.find(f"{G}image_link").text == "https://cdn.test/baguete.jpg"
    assert item.find(f"{G}brand").text == "Nelson Boulangerie"
    assert item.find(f"{G}identifier_exists").text == "no"
    # custom_label_0 = coleção primária (análogo smart collection p/ anúncios)
    assert item.find(f"{G}custom_label_0").text == "paes"
    assert item.find(f"{G}product_type").text == "Pães"


def test_paused_product_is_out_of_stock(client, feed_surface):
    feed_surface["com_foto"].is_sellable = False
    feed_surface["com_foto"].save()
    item = _items(client.get("/feed/google.xml").content)[0]
    assert item.find(f"{G}availability").text == "out_of_stock"


def test_smart_collection_feed(client, db):
    Channel.objects.create(
        ref="meta",
        name="Meta",
        is_active=True,
        config={"capability": "feed", "content": {"source": "collection", "collection": "caros"}},
    )
    Collection.objects.create(
        ref="caros", name="Caros", is_active=True,
        rule={"match": "all", "conditions": [{"field": "base_price_q", "op": "gte", "value": 1000}]},
    )
    Product.objects.create(
        sku="BOLO", name="Bolo", unit="un", base_price_q=4500, is_published=True, is_sellable=True,
        image_url="https://cdn.test/bolo.jpg",
    )
    Product.objects.create(
        sku="PAO", name="Pão", unit="un", base_price_q=500, is_published=True, is_sellable=True,
        image_url="https://cdn.test/pao.jpg",
    )
    items = _items(client.get("/feed/meta.xml").content)
    assert [i.find(f"{G}id").text for i in items] == ["BOLO"]  # só >= R$10 pela regra


def test_non_feed_surface_404(client, db):
    Channel.objects.create(ref="web", name="Web", is_active=True)  # capability transactional
    assert client.get("/feed/web.xml").status_code == 404


def test_display_surface_is_not_a_feed(client, db):
    Channel.objects.create(
        ref="tv", name="TV", is_active=True,
        config={"capability": "display", "content": {"source": "collection", "collection": "x"}},
    )
    assert client.get("/feed/tv.xml").status_code == 404
