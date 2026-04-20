"""Tests for storefront catalog views: MenuView, ProductDetailView."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

pytestmark = pytest.mark.django_db


# ── MenuView ──────────────────────────────────────────────────────────


class TestMenuView:
    def test_menu_empty(self, client: Client):
        resp = client.get("/menu/")
        assert resp.status_code == 200

    def test_menu_with_products(self, client: Client, collection, collection_item, product, listing_item):
        resp = client.get("/menu/")
        assert resp.status_code == 200
        assert b"paes" in resp.content.lower() or b"P\xc3\xa3es" in resp.content

    def test_menu_filtered_by_collection(self, client: Client, collection, collection_item, product):
        resp = client.get(f"/menu/{collection.ref}/")
        assert resp.status_code == 200

    def test_menu_collection_not_found(self, client: Client):
        resp = client.get("/menu/inexistente/")
        assert resp.status_code == 404

    def test_menu_inactive_collection_404(self, client: Client, collection_inactive):
        resp = client.get(f"/menu/{collection_inactive.ref}/")
        assert resp.status_code == 404

    def test_menu_hides_unpublished_products(self, client: Client, collection, product_unpublished):
        from shopman.offerman.models import CollectionItem
        CollectionItem.objects.create(collection=collection, product=product_unpublished, sort_order=1)
        resp = client.get(f"/menu/{collection.ref}/")
        assert resp.status_code == 200
        assert b"Rascunho" not in resp.content

    def test_menu_uncategorized_products(self, client: Client, product):
        """Products not in any collection appear in an uncategorized section."""
        resp = client.get("/menu/")
        assert resp.status_code == 200

    def test_menu_sets_csrf_cookie(self, client: Client):
        resp = client.get("/menu/")
        assert "csrftoken" in resp.cookies


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

    def test_product_detail_uses_canonical_price_quote_for_promotion(
        self,
        client: Client,
        product,
        listing_item,
        channel,
    ):
        from shopman.storefront.models import Promotion

        now = timezone.now()
        Promotion.objects.create(
            name="Promo Web",
            type=Promotion.FIXED,
            value=10,
            valid_from=now - timedelta(hours=1),
            valid_until=now + timedelta(hours=1),
            skus=[product.sku],
            is_active=True,
        )

        resp = client.get(f"/produto/{product.sku}/")
        assert resp.status_code == 200
        projection = resp.context["product"]
        assert projection.base_price_q == 80
        assert projection.has_promotion is True
        assert projection.price_display == "R$ 0,80"
        assert projection.original_price_display == "R$ 0,90"
        assert projection.promotion_label is not None

    def test_pdp_shows_indisponivel_badge_when_paused(self, client: Client, product_unavailable):
        """PDP de produto indisponível mostra badge 'Indisponível' e NÃO exibe
        seção de substitutos (AVAILABILITY-PLAN §5 — substitutos só no modal)."""
        resp = client.get(f"/produto/{product_unavailable.sku}/")
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "Indisponível" in body
        # Qualquer título de seção que pudesse sugerir substitutos deve estar ausente.
        for forbidden in ("Outras opções", "No lugar deste", "Veja alternativas", "Substitutos"):
            assert forbidden not in body, f"PDP não deve listar substitutos ('{forbidden}' vazou)"

    def test_pdp_never_shows_substitutes_section_when_available(self, client: Client, product):
        """Mesmo com produto disponível, PDP nunca renderiza seção de substitutos."""
        resp = client.get(f"/produto/{product.sku}/")
        assert resp.status_code == 200
        body = resp.content.decode()
        for forbidden in ("Outras opções", "No lugar deste", "Veja alternativas", "Substitutos"):
            assert forbidden not in body
