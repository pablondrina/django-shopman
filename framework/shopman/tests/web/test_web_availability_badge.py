"""Tests for HTMX availability badges in storefront — WP-CL2-12."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product

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
        is_available=True,
    )


@pytest.fixture
def product_in_listing(product, db):
    listing = Listing.objects.create(ref="balcao", name="Balcão", is_active=True, priority=10)
    ListingItem.objects.create(
        listing=listing,
        product=product,
        price_q=150,
        is_published=True,
        is_available=False,  # sold-out in listing so badge shows
    )
    return product


@pytest.fixture
def product_unavailable(db):
    return Product.objects.create(
        sku="BOLO-BADGE",
        name="Bolo Indisponível",
        base_price_q=500,
        is_published=True,
        is_available=False,
    )


class TestAvailabilityBadgePartialSSR:
    """SSR renders availability badge with correct initial class and hx-get attribute."""

    def test_product_detail_sold_out_renders_badge_with_hx_get(self, client, product_unavailable):
        resp = client.get(f"/produto/{product_unavailable.sku}/")
        assert resp.status_code == 200
        content = resp.content.decode()
        # Badge partial is rendered when badge.label is truthy (unavailable product)
        assert "availability-badge" in content
        assert "hx-get" in content
        assert f"/api/availability/{product_unavailable.sku}/" in content

    def test_product_detail_badge_has_correct_class(self, client, product_unavailable):
        resp = client.get(f"/produto/{product_unavailable.sku}/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "badge-unavailable" in content

    def test_product_detail_badge_has_htmx_trigger(self, client, product_unavailable):
        resp = client.get(f"/produto/{product_unavailable.sku}/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "every 30s" in content

    def test_product_detail_badge_has_channel_param(self, client, product_unavailable):
        resp = client.get(f"/produto/{product_unavailable.sku}/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "?channel=web" in content

    def test_product_detail_badge_outerhtml_swap(self, client, product_unavailable):
        """Badge partial uses outerHTML swap so HTMX replaces the entire element on poll."""
        resp = client.get(f"/produto/{product_unavailable.sku}/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert 'hx-swap="outerHTML"' in content
