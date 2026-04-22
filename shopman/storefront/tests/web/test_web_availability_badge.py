"""Tests for HTMX availability badges in storefront — WP-CL2-12."""

from __future__ import annotations

import pytest
from shopman.offerman.models import Listing, ListingItem, Product

pytestmark = pytest.mark.django_db

AVAILABLE_RESULT = {
    "ok": True,
    "available_qty": __import__("decimal").Decimal("100"),
    "is_paused": False,
    "is_planned": False,
    "breakdown": {},
    "error_code": None,
    "is_bundle": False,
    "failed_sku": None,
    "untracked": True,
}

SOLD_OUT_RESULT = {
    "ok": False,
    "available_qty": __import__("decimal").Decimal("0"),
    "is_paused": False,
    "is_planned": False,
    "breakdown": {},
    "error_code": "insufficient_stock",
    "is_bundle": False,
    "failed_sku": None,
}


@pytest.fixture
def product(db):
    return Product.objects.create(
        sku="PAO-BADGE",
        name="Pão Artesanal",
        base_price_q=150,
        is_published=True,
        is_sellable=True,
    )


@pytest.fixture
def product_in_listing(product, db):
    listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True, priority=10)
    ListingItem.objects.create(
        listing=listing,
        product=product,
        price_q=150,
        is_published=True,
        is_sellable=False,  # strategically unavailable in listing
    )
    return product


@pytest.fixture
def product_unavailable(db):
    return Product.objects.create(
        sku="BOLO-BADGE",
        name="Bolo Indisponível",
        base_price_q=500,
        is_published=True,
        is_sellable=False,
    )


class TestAvailabilityBadgePartialSSR:
    """v2 product detail renders static availability badge from projection."""

    def test_product_detail_sold_out_renders_unavailable_badge(self, client, product_unavailable):
        resp = client.get(f"/produto/{product_unavailable.sku}/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Indisponível" in content

    def test_product_detail_badge_has_correct_class(self, client, product_unavailable):
        resp = client.get(f"/produto/{product_unavailable.sku}/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "badge-neutral" in content

    def test_product_detail_available_renders_200(self, client, product):
        resp = client.get(f"/produto/{product.sku}/")
        assert resp.status_code == 200
