"""Tests for Offerman REST API (SPEC-001)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from shopman.offerman.models import (
    Collection,
    CollectionItem,
    Listing,
    ListingItem,
    Product,
    ProductComponent,
)


@pytest.fixture
def user(db):
    """Create an authenticated user."""
    return User.objects.create_user(username="agent", password="testpass123")


@pytest.fixture
def api_client(user):
    """Return an authenticated API client."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def anon_client():
    """Return an unauthenticated API client."""
    return APIClient()


# ─── Data fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def breads_collection(db):
    return Collection.objects.create(ref="breads", name="Breads", is_active=True)


@pytest.fixture
def inactive_collection(db):
    return Collection.objects.create(ref="archived", name="Archived", is_active=False)


@pytest.fixture
def baguete(db, breads_collection):
    prod = Product.objects.create(
        sku="BAGUETE",
        name="Baguete Tradicional",
        short_description="French baguette",
        long_description="Traditional French baguette with natural fermentation",
        unit="un",
        base_price_q=500,
        is_published=True,
        is_available=True,
    )
    prod.keywords.add("artesanal", "fermentacao-natural")
    CollectionItem.objects.create(collection=breads_collection, product=prod, is_primary=True)
    return prod


@pytest.fixture
def croissant(db, breads_collection):
    prod = Product.objects.create(
        sku="CROISSANT",
        name="Croissant Clássico",
        short_description="Classic croissant",
        unit="un",
        base_price_q=800,
        shelf_life_days=12,
        production_cycle_hours=4,
        is_published=True,
        is_available=True,
    )
    prod.keywords.add("artesanal", "manteiga")
    CollectionItem.objects.create(collection=breads_collection, product=prod, is_primary=True)
    return prod


@pytest.fixture
def coffee(db):
    return Product.objects.create(
        sku="COFFEE",
        name="Espresso Coffee",
        unit="un",
        base_price_q=500,
        is_published=True,
        is_available=True,
    )


@pytest.fixture
def hidden_product(db, breads_collection):
    prod = Product.objects.create(
        sku="HIDDEN-001",
        name="Hidden Product",
        base_price_q=1000,
        is_published=False,
    )
    CollectionItem.objects.create(collection=breads_collection, product=prod)
    return prod


@pytest.fixture
def paused_product(db, breads_collection):
    prod = Product.objects.create(
        sku="PAUSED-001",
        name="Paused Product",
        base_price_q=1000,
        is_available=False,
    )
    CollectionItem.objects.create(collection=breads_collection, product=prod)
    return prod


@pytest.fixture
def combo(db, breads_collection, croissant, coffee):
    combo = Product.objects.create(
        sku="COMBO-CAFE",
        name="Breakfast Combo",
        base_price_q=1100,
        is_published=True,
        is_available=True,
    )
    CollectionItem.objects.create(collection=breads_collection, product=combo, is_primary=True)
    ProductComponent.objects.create(parent=combo, component=croissant, qty=Decimal("1"))
    ProductComponent.objects.create(parent=combo, component=coffee, qty=Decimal("2"))
    return combo


@pytest.fixture
def ifood_listing(db):
    return Listing.objects.create(
        ref="ifood",
        name="iFood Prices",
        is_active=True,
        priority=10,
    )


@pytest.fixture
def balcao_listing(db):
    return Listing.objects.create(
        ref="balcao",
        name="Balcão",
        is_active=True,
        priority=0,
    )


@pytest.fixture
def inactive_listing(db):
    return Listing.objects.create(
        ref="promo-old",
        name="Old Promo",
        is_active=False,
    )


@pytest.fixture
def ifood_baguete(db, ifood_listing, baguete):
    return ListingItem.objects.create(
        listing=ifood_listing,
        product=baguete,
        price_q=600,
    )


@pytest.fixture
def ifood_croissant(db, ifood_listing, croissant):
    return ListingItem.objects.create(
        listing=ifood_listing,
        product=croissant,
        price_q=950,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  PRODUCTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestProductList:
    """GET /api/offering/products/"""

    def test_list_returns_active_products(self, api_client, baguete, croissant):
        resp = api_client.get("/api/offering/products/")
        assert resp.status_code == 200
        results = resp.data["results"]
        skus = {p["sku"] for p in results}
        assert "BAGUETE" in skus
        assert "CROISSANT" in skus

    def test_list_excludes_unpublished(self, api_client, baguete, hidden_product):
        resp = api_client.get("/api/offering/products/")
        skus = {p["sku"] for p in resp.data["results"]}
        assert "BAGUETE" in skus
        assert "HIDDEN-001" not in skus

    def test_list_excludes_unavailable(self, api_client, baguete, paused_product):
        resp = api_client.get("/api/offering/products/")
        skus = {p["sku"] for p in resp.data["results"]}
        assert "BAGUETE" in skus
        assert "PAUSED-001" not in skus

    def test_filter_by_collection(self, api_client, baguete, coffee):
        resp = api_client.get("/api/offering/products/", {"collection": "breads"})
        skus = {p["sku"] for p in resp.data["results"]}
        assert "BAGUETE" in skus
        assert "COFFEE" not in skus

    def test_filter_by_unit(self, api_client, baguete, croissant):
        resp = api_client.get("/api/offering/products/", {"unit": "un"})
        assert resp.status_code == 200
        for p in resp.data["results"]:
            assert p["unit"] == "un"

    def test_search_by_name(self, api_client, baguete, croissant):
        resp = api_client.get("/api/offering/products/", {"search": "Baguete"})
        assert resp.status_code == 200
        skus = {p["sku"] for p in resp.data["results"]}
        assert "BAGUETE" in skus
        assert "CROISSANT" not in skus

    def test_search_by_sku(self, api_client, baguete, croissant):
        resp = api_client.get("/api/offering/products/", {"search": "CROISSANT"})
        skus = {p["sku"] for p in resp.data["results"]}
        assert "CROISSANT" in skus

    def test_search_by_keyword(self, api_client, baguete, croissant):
        resp = api_client.get("/api/offering/products/", {"search": "manteiga"})
        skus = {p["sku"] for p in resp.data["results"]}
        assert "CROISSANT" in skus
        assert "BAGUETE" not in skus

    def test_pagination(self, api_client, baguete, croissant):
        resp = api_client.get("/api/offering/products/")
        assert "count" in resp.data
        assert "results" in resp.data

    def test_serializer_fields(self, api_client, baguete):
        resp = api_client.get("/api/offering/products/")
        product = resp.data["results"][0]
        expected_fields = {
            "uuid", "sku", "name", "short_description", "unit",
            "base_price_q", "is_published", "is_available",
            "availability_policy", "keywords",
        }
        assert set(product.keys()) == expected_fields

    def test_keywords_serialized_as_list(self, api_client, baguete):
        resp = api_client.get("/api/offering/products/")
        product = resp.data["results"][0]
        assert isinstance(product["keywords"], list)
        assert "artesanal" in product["keywords"]


class TestProductDetail:
    """GET /api/offering/products/{sku}/"""

    def test_retrieve_by_sku(self, api_client, baguete):
        resp = api_client.get(f"/api/offering/products/{baguete.sku}/")
        assert resp.status_code == 200
        assert resp.data["sku"] == "BAGUETE"
        assert resp.data["name"] == "Baguete Tradicional"

    def test_detail_includes_long_description(self, api_client, baguete):
        resp = api_client.get(f"/api/offering/products/{baguete.sku}/")
        assert "long_description" in resp.data

    def test_detail_includes_shelf_life(self, api_client, croissant):
        resp = api_client.get(f"/api/offering/products/{croissant.sku}/")
        assert resp.data["shelf_life_days"] == 12
        assert resp.data["production_cycle_hours"] == 4

    def test_detail_includes_components_for_bundle(self, api_client, combo):
        resp = api_client.get(f"/api/offering/products/{combo.sku}/")
        assert resp.status_code == 200
        assert "components" in resp.data
        assert len(resp.data["components"]) == 2
        component_skus = {c["component_sku"] for c in resp.data["components"]}
        assert component_skus == {"CROISSANT", "COFFEE"}

    def test_detail_components_empty_for_non_bundle(self, api_client, baguete):
        resp = api_client.get(f"/api/offering/products/{baguete.sku}/")
        assert resp.data["components"] == []

    def test_404_for_nonexistent_sku(self, api_client):
        resp = api_client.get("/api/offering/products/DOESNOTEXIST/")
        assert resp.status_code == 404

    def test_404_for_unpublished_product(self, api_client, hidden_product):
        resp = api_client.get(f"/api/offering/products/{hidden_product.sku}/")
        assert resp.status_code == 404


class TestProductPrice:
    """GET /api/offering/products/{sku}/price/"""

    def test_price_with_base_price(self, api_client, baguete):
        resp = api_client.get(
            f"/api/offering/products/{baguete.sku}/price/",
            {"channel_ref": "balcao"},
        )
        assert resp.status_code == 200
        assert resp.data["sku"] == "BAGUETE"
        assert resp.data["unit_price_q"] == 500
        assert resp.data["total_q"] == 500
        assert resp.data["currency"] == "BRL"

    def test_price_with_qty(self, api_client, baguete):
        resp = api_client.get(
            f"/api/offering/products/{baguete.sku}/price/",
            {"channel_ref": "balcao", "qty": "3"},
        )
        assert resp.status_code == 200
        assert resp.data["total_q"] == 1500

    def test_price_from_listing(self, api_client, baguete, ifood_baguete):
        resp = api_client.get(
            f"/api/offering/products/{baguete.sku}/price/",
            {"channel_ref": "ifood"},
        )
        assert resp.status_code == 200
        assert resp.data["unit_price_q"] == 600
        assert resp.data["total_q"] == 600

    def test_price_from_explicit_listing(self, api_client, baguete, ifood_baguete):
        resp = api_client.get(
            f"/api/offering/products/{baguete.sku}/price/",
            {"channel_ref": "balcao", "listing_ref": "ifood"},
        )
        assert resp.status_code == 200
        assert resp.data["unit_price_q"] == 600

    def test_price_requires_channel_ref(self, api_client, baguete):
        resp = api_client.get(f"/api/offering/products/{baguete.sku}/price/")
        assert resp.status_code == 400

    def test_price_invalid_qty(self, api_client, baguete):
        resp = api_client.get(
            f"/api/offering/products/{baguete.sku}/price/",
            {"channel_ref": "balcao", "qty": "abc"},
        )
        assert resp.status_code == 400

    def test_price_zero_qty(self, api_client, baguete):
        resp = api_client.get(
            f"/api/offering/products/{baguete.sku}/price/",
            {"channel_ref": "balcao", "qty": "0"},
        )
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
#  COLLECTIONS
# ═══════════════════════════════════════════════════════════════════════════════


class TestCollectionList:
    """GET /api/offering/collections/"""

    def test_list_active_collections(self, api_client, breads_collection):
        resp = api_client.get("/api/offering/collections/")
        assert resp.status_code == 200
        slugs = {c["ref"] for c in resp.data["results"]}
        assert "breads" in slugs

    def test_excludes_inactive_collections(self, api_client, breads_collection, inactive_collection):
        resp = api_client.get("/api/offering/collections/")
        slugs = {c["ref"] for c in resp.data["results"]}
        assert "breads" in slugs
        assert "archived" not in slugs

    def test_collection_serializer_fields(self, api_client, breads_collection):
        resp = api_client.get("/api/offering/collections/")
        coll = resp.data["results"][0]
        expected = {"uuid", "ref", "name", "description", "is_active"}
        assert set(coll.keys()) == expected


class TestCollectionDetail:
    """GET /api/offering/collections/{slug}/"""

    def test_retrieve_by_slug(self, api_client, breads_collection, baguete):
        resp = api_client.get(f"/api/offering/collections/{breads_collection.ref}/")
        assert resp.status_code == 200
        assert resp.data["ref"] == "breads"

    def test_detail_includes_products(self, api_client, breads_collection, baguete, croissant):
        resp = api_client.get(f"/api/offering/collections/{breads_collection.ref}/")
        assert "products" in resp.data
        product_skus = {p["sku"] for p in resp.data["products"]}
        assert "BAGUETE" in product_skus
        assert "CROISSANT" in product_skus

    def test_detail_products_include_primary_flag(self, api_client, breads_collection, baguete):
        resp = api_client.get(f"/api/offering/collections/{breads_collection.ref}/")
        product = resp.data["products"][0]
        assert "is_primary" in product
        assert "sort_order" in product

    def test_404_for_nonexistent_collection(self, api_client):
        resp = api_client.get("/api/offering/collections/nonexistent/")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
#  LISTINGS
# ═══════════════════════════════════════════════════════════════════════════════


class TestListingList:
    """GET /api/offering/listings/"""

    def test_list_active_listings(self, api_client, ifood_listing, balcao_listing):
        resp = api_client.get("/api/offering/listings/")
        assert resp.status_code == 200
        codes = {pl["ref"] for pl in resp.data["results"]}
        assert "ifood" in codes
        assert "balcao" in codes

    def test_excludes_inactive_listings(self, api_client, ifood_listing, inactive_listing):
        resp = api_client.get("/api/offering/listings/")
        codes = {pl["ref"] for pl in resp.data["results"]}
        assert "ifood" in codes
        assert "promo-old" not in codes


class TestListingItems:
    """GET /api/offering/listings/{code}/items/"""

    def test_list_items(self, api_client, ifood_listing, ifood_baguete, ifood_croissant):
        resp = api_client.get(f"/api/offering/listings/{ifood_listing.ref}/items/")
        assert resp.status_code == 200
        assert len(resp.data) == 2
        skus = {item["sku"] for item in resp.data}
        assert skus == {"BAGUETE", "CROISSANT"}

    def test_filter_items_by_sku(self, api_client, ifood_listing, ifood_baguete, ifood_croissant):
        resp = api_client.get(
            f"/api/offering/listings/{ifood_listing.ref}/items/",
            {"sku": "BAGUETE"},
        )
        assert resp.status_code == 200
        assert len(resp.data) == 1
        assert resp.data[0]["sku"] == "BAGUETE"
        assert resp.data[0]["price_q"] == 600

    def test_item_serializer_fields(self, api_client, ifood_listing, ifood_baguete):
        resp = api_client.get(f"/api/offering/listings/{ifood_listing.ref}/items/")
        item = resp.data[0]
        expected = {"sku", "product_name", "price_q", "min_qty", "is_published", "is_available"}
        assert set(item.keys()) == expected


# ═══════════════════════════════════════════════════════════════════════════════
#  READ-ONLY ENFORCEMENT
# ═══════════════════════════════════════════════════════════════════════════════


class TestReadOnly:
    """All endpoints must reject write operations (POST/PUT/PATCH/DELETE)."""

    def test_products_post_returns_405(self, api_client, baguete):
        resp = api_client.post("/api/offering/products/", {"sku": "NEW"})
        assert resp.status_code == 405

    def test_products_put_returns_405(self, api_client, baguete):
        resp = api_client.put(f"/api/offering/products/{baguete.sku}/", {"name": "X"})
        assert resp.status_code == 405

    def test_products_patch_returns_405(self, api_client, baguete):
        resp = api_client.patch(f"/api/offering/products/{baguete.sku}/", {"name": "X"})
        assert resp.status_code == 405

    def test_products_delete_returns_405(self, api_client, baguete):
        resp = api_client.delete(f"/api/offering/products/{baguete.sku}/")
        assert resp.status_code == 405

    def test_collections_post_returns_405(self, api_client, breads_collection):
        resp = api_client.post("/api/offering/collections/", {"ref": "new"})
        assert resp.status_code == 405

    def test_collections_delete_returns_405(self, api_client, breads_collection):
        resp = api_client.delete(f"/api/offering/collections/{breads_collection.ref}/")
        assert resp.status_code == 405

    def test_listings_post_returns_405(self, api_client, ifood_listing):
        resp = api_client.post("/api/offering/listings/", {"ref": "new"})
        assert resp.status_code == 405


# ═══════════════════════════════════════════════════════════════════════════════
#  AUTHENTICATION
# ═══════════════════════════════════════════════════════════════════════════════


class TestAuthentication:
    """Offerman endpoints are public (AllowAny) — catalog is accessible without auth."""

    def test_products_accessible_without_auth(self, anon_client, baguete):
        resp = anon_client.get("/api/offering/products/")
        assert resp.status_code == 200

    def test_product_detail_accessible_without_auth(self, anon_client, baguete):
        resp = anon_client.get(f"/api/offering/products/{baguete.sku}/")
        assert resp.status_code == 200

    def test_product_price_accessible_without_auth(self, anon_client, baguete):
        resp = anon_client.get(
            f"/api/offering/products/{baguete.sku}/price/",
            {"channel_ref": "balcao"},
        )
        # 400 because channel doesn't exist in this fixture, but NOT 403
        assert resp.status_code != 403

    def test_collections_accessible_without_auth(self, anon_client, breads_collection):
        resp = anon_client.get("/api/offering/collections/")
        assert resp.status_code == 200

    def test_listings_accessible_without_auth(self, anon_client, ifood_listing):
        resp = anon_client.get("/api/offering/listings/")
        assert resp.status_code == 200
