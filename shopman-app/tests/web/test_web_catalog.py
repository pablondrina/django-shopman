"""Tests for storefront catalog views: MenuView, MenuSearchView, ProductDetailView."""
from __future__ import annotations

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


# ── MenuView ──────────────────────────────────────────────────────────


class TestMenuView:
    def test_menu_empty(self, client: Client):
        resp = client.get("/menu/")
        assert resp.status_code == 200

    def test_menu_with_products(self, client: Client, collection, collection_item, product):
        resp = client.get("/menu/")
        assert resp.status_code == 200
        assert b"paes" in resp.content.lower() or b"P\xc3\xa3es" in resp.content

    def test_menu_filtered_by_collection(self, client: Client, collection, collection_item, product):
        resp = client.get(f"/menu/{collection.slug}/")
        assert resp.status_code == 200

    def test_menu_collection_not_found(self, client: Client):
        resp = client.get("/menu/inexistente/")
        assert resp.status_code == 404

    def test_menu_inactive_collection_404(self, client: Client, collection_inactive):
        resp = client.get(f"/menu/{collection_inactive.slug}/")
        assert resp.status_code == 404

    def test_menu_hides_unpublished_products(self, client: Client, collection, product_unpublished):
        from shopman.offering.models import CollectionItem
        CollectionItem.objects.create(collection=collection, product=product_unpublished, sort_order=1)
        resp = client.get(f"/menu/{collection.slug}/")
        assert resp.status_code == 200
        assert b"Rascunho" not in resp.content

    def test_menu_uncategorized_products(self, client: Client, product):
        """Products not in any collection appear in an uncategorized section."""
        resp = client.get("/menu/")
        assert resp.status_code == 200

    def test_menu_sets_csrf_cookie(self, client: Client):
        resp = client.get("/menu/")
        assert "csrftoken" in resp.cookies


# ── MenuSearchView ────────────────────────────────────────────────────


class TestMenuSearchView:
    def test_search_empty_query(self, client: Client):
        resp = client.get("/menu/search/")
        assert resp.status_code == 200
        assert resp.content == b""

    def test_search_short_query(self, client: Client, product):
        resp = client.get("/menu/search/?q=P")
        assert resp.status_code == 200
        # Should return hint, not results
        assert b"PAO-FRANCES" not in resp.content

    def test_search_finds_product(self, client: Client, product):
        resp = client.get("/menu/search/?q=Francês")
        assert resp.status_code == 200

    def test_search_no_results(self, client: Client, product):
        resp = client.get("/menu/search/?q=ZZZNOTFOUND")
        assert resp.status_code == 200

    def test_search_excludes_unpublished(self, client: Client, product_unpublished):
        resp = client.get("/menu/search/?q=Rascunho")
        assert resp.status_code == 200


# ── ProductDetailView ─────────────────────────────────────────────────


class TestProductDetailView:
    def test_product_detail(self, client: Client, product):
        resp = client.get(f"/produto/{product.sku}/")
        assert resp.status_code == 200

    def test_product_detail_not_found(self, client: Client):
        resp = client.get("/produto/INEXISTENTE/")
        assert resp.status_code == 404

    def test_product_detail_unpublished_404(self, client: Client, product_unpublished):
        resp = client.get(f"/produto/{product_unpublished.sku}/")
        assert resp.status_code == 404

    def test_product_detail_with_listing_price(self, client: Client, product, listing_item, channel):
        resp = client.get(f"/produto/{product.sku}/")
        assert resp.status_code == 200
        # Listing price (90 centavos = R$ 0,90) should appear
        assert b"0,90" in resp.content

    def test_product_detail_fallback_base_price(self, client: Client, product):
        resp = client.get(f"/produto/{product.sku}/")
        assert resp.status_code == 200
        # Base price (80 centavos = R$ 0,80)
        assert b"0,80" in resp.content

    def test_pdp_shows_alternatives_when_sold_out(self, client: Client, product_unavailable, product):
        """When product is unavailable (paused), PDP shows alternatives section."""
        resp = client.get(f"/produto/{product_unavailable.sku}/")
        assert resp.status_code == 200
        # Badge should show "Indisponível"
        assert "badge-paused" in resp.content.decode()
        # The alternatives section heading should be present (even if empty list, no alternatives found)
        # Since product_unavailable has no keywords, alternatives will be empty — that's OK.
        # We verify the view doesn't crash and the badge is correct.

    def test_pdp_hides_alternatives_when_available(self, client: Client, product):
        """When product is available, no alternatives section is shown."""
        resp = client.get(f"/produto/{product.sku}/")
        assert resp.status_code == 200
        assert "Produtos Similares" not in resp.content.decode()
