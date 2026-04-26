from __future__ import annotations

from decimal import Decimal

import pytest

from shopman.shop.services import catalog_exports

pytestmark = pytest.mark.django_db


def _listing_with_product(*, is_published: bool = True, is_sellable: bool = True):
    from shopman.offerman.models import Listing, ListingItem, Product

    listing = Listing.objects.create(ref="google", name="Google", is_active=True)
    product = Product.objects.create(
        sku="PAO-FRANCES",
        name="Pão Francês",
        short_description="Pão crocante",
        long_description="Pão francês artesanal",
        unit="un",
        base_price_q=80,
        image_url="https://cdn.example.test/pao.jpg",
        metadata={
            "brand": "Demo Bakery",
            "gallery": ["https://cdn.example.test/pao-2.jpg"],
        },
        is_published=is_published,
        is_sellable=is_sellable,
    )
    item = ListingItem.objects.create(
        listing=listing,
        product=product,
        price_q=90,
        is_published=is_published,
        is_sellable=is_sellable,
    )
    return listing, product, item


def test_build_catalog_export_returns_neutral_payload(monkeypatch):
    listing, product, _item = _listing_with_product()

    monkeypatch.setattr(
        "shopman.shop.services.catalog_context.availability_for_sku",
        lambda sku, *, channel_ref: {
            "total_promisable": Decimal("3"),
            "availability_policy": "planned_ok",
            "is_paused": False,
            "is_planned": False,
        },
    )

    payload = catalog_exports.build_catalog_export(listing_ref=listing.ref, channel="google")

    assert payload.listing == "google"
    assert payload.channel == "google"
    assert payload.status == "active"
    assert len(payload.items) == 1

    item = payload.items[0]
    assert item.product == str(product.uuid)
    assert item.listing == "google"
    assert item.ref == "google:PAO-FRANCES"
    assert item.sku == "PAO-FRANCES"
    assert item.name == "Pão Francês"
    assert item.description == "Pão francês artesanal"
    assert item.images == (
        "https://cdn.example.test/pao.jpg",
        "https://cdn.example.test/pao-2.jpg",
    )
    assert item.price.amount_q == 90
    assert item.price.currency == "BRL"
    assert item.availability.status == "low_stock"
    assert item.availability.available_qty == 3
    assert item.availability.channel == "google"
    assert item.channel == "google"
    assert item.status == "active"
    assert item.metadata["brand"] == "Demo Bakery"
    assert "gallery" not in item.metadata


def test_build_catalog_export_dict_is_serializable(monkeypatch):
    listing, _product, _item = _listing_with_product()
    monkeypatch.setattr(
        "shopman.shop.services.catalog_context.availability_for_sku",
        lambda sku, *, channel_ref: None,
    )

    data = catalog_exports.build_catalog_export_dict(listing_ref=listing.ref)

    assert data["metadata"]["contract"] == "catalog_export.v1"
    assert data["items"][0]["price"]["amount_q"] == 90
    assert data["items"][0]["availability"]["status"] == "available"


def test_inactive_items_are_omitted_by_default_and_available_when_requested(monkeypatch):
    listing, _product, _item = _listing_with_product(is_sellable=False)
    monkeypatch.setattr(
        "shopman.shop.services.catalog_context.availability_for_sku",
        lambda sku, *, channel_ref: None,
    )

    default_payload = catalog_exports.build_catalog_export(listing_ref=listing.ref)
    full_payload = catalog_exports.build_catalog_export(
        listing_ref=listing.ref,
        include_inactive=True,
    )

    assert default_payload.items == ()
    assert default_payload.status == "empty"
    assert len(full_payload.items) == 1
    assert full_payload.items[0].status == "paused"
    assert full_payload.items[0].availability.status == "unavailable"
