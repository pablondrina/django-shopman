"""Tests for Offerman service (CatalogService API)."""

from decimal import Decimal

import pytest

from shopman.offerman.service import CatalogService
from shopman.offerman.exceptions import CatalogError
from shopman.offerman.models import Collection, CollectionItem, Product, Listing, ListingItem


pytestmark = pytest.mark.django_db


class TestCatalogGet:
    """Tests for CatalogService.get()."""

    def test_get_single_product(self, db):
        """Test getting single product by SKU."""
        product = Product.objects.create(sku="BAGUETE", name="Baguete")
        result = CatalogService.get("BAGUETE")
        assert result == product

    def test_get_nonexistent(self, db):
        """Test getting nonexistent product."""
        result = CatalogService.get("NONEXISTENT")
        assert result is None

    def test_get_multiple_products(self, db):
        """Test getting multiple products."""
        product = Product.objects.create(sku="BAGUETE", name="Baguete")
        croissant = Product.objects.create(sku="CROISSANT", name="Croissant")

        result = CatalogService.get(["BAGUETE", "CROISSANT"])
        assert len(result) == 2
        assert result["BAGUETE"] == product
        assert result["CROISSANT"] == croissant

    def test_get_multiple_partial(self, db):
        """Test getting multiple with some missing."""
        Product.objects.create(sku="BAGUETE", name="Baguete")

        result = CatalogService.get(["BAGUETE", "NONEXISTENT"])
        assert len(result) == 1
        assert "BAGUETE" in result


class TestCatalogPrice:
    """Tests for CatalogService.price()."""

    def test_price_base(self, db):
        """Test base price."""
        Product.objects.create(sku="BAGUETE", name="Baguete", base_price_q=500)
        price = CatalogService.price("BAGUETE")
        assert price == 500  # R$ 5.00 in cents

    def test_price_with_quantity(self, db):
        """Test price with quantity."""
        Product.objects.create(sku="BAGUETE", name="Baguete", base_price_q=500)
        price = CatalogService.price("BAGUETE", qty=Decimal("3"))
        assert price == 1500  # 3 x R$ 5.00

    def test_price_from_listing(self, db):
        """Test price from listing."""
        product = Product.objects.create(sku="BAGUETE", name="Baguete", base_price_q=500)
        listing = Listing.objects.create(ref="ifood", name="iFood")
        ListingItem.objects.create(listing=listing, product=product, price_q=600)

        price = CatalogService.price("BAGUETE", channel="ifood")
        assert price == 600  # R$ 6.00 from iFood listing

    def test_price_fallback_to_base(self, db):
        """Test fallback to base price when no listing."""
        Product.objects.create(sku="BAGUETE", name="Baguete", base_price_q=500)
        price = CatalogService.price("BAGUETE", channel="nonexistent")
        assert price == 500  # Fallback to base

    def test_price_nonexistent_product(self, db):
        """Test price for nonexistent product."""
        with pytest.raises(CatalogError) as exc:
            CatalogService.price("NONEXISTENT")
        assert exc.value.code == "SKU_NOT_FOUND"


class TestCatalogExpand:
    """Tests for CatalogService.expand()."""

    def test_expand_bundle(self, db):
        """Test expanding bundle."""
        from shopman.offerman.models import ProductComponent

        combo = Product.objects.create(sku="COMBO-CAFE", name="Combo Café")
        croissant = Product.objects.create(sku="CROISSANT", name="Croissant")
        coffee = Product.objects.create(sku="COFFEE", name="Coffee")

        ProductComponent.objects.create(parent=combo, component=croissant, qty=Decimal("1"))
        ProductComponent.objects.create(parent=combo, component=coffee, qty=Decimal("1"))

        components = CatalogService.expand("COMBO-CAFE")
        assert len(components) == 2

        skus = [c["sku"] for c in components]
        assert "CROISSANT" in skus
        assert "COFFEE" in skus

    def test_expand_non_bundle(self, db):
        """Test expanding non-bundle product."""
        Product.objects.create(sku="BAGUETE", name="Baguete")

        with pytest.raises(CatalogError) as exc:
            CatalogService.expand("BAGUETE")
        assert exc.value.code == "NOT_A_BUNDLE"

    def test_expand_nonexistent(self, db):
        """Test expanding nonexistent product."""
        with pytest.raises(CatalogError) as exc:
            CatalogService.expand("NONEXISTENT")
        assert exc.value.code == "SKU_NOT_FOUND"


class TestCatalogValidate:
    """Tests for CatalogService.validate()."""

    def test_validate_valid_product(self, db):
        """Test validating valid product."""
        Product.objects.create(sku="BAGUETE", name="Baguete Tradicional")

        result = CatalogService.validate("BAGUETE")
        assert result.valid is True
        assert result.sku == "BAGUETE"
        assert result.name == "Baguete Tradicional"
        assert result.is_published is True
        assert result.is_sellable is True
        assert result.message is None

    def test_validate_unpublished_product(self, db):
        """Test validating unpublished product."""
        Product.objects.create(sku="HIDDEN-001", name="Hidden", is_published=False)

        result = CatalogService.validate("HIDDEN-001")
        assert result.valid is True
        assert result.is_published is False
        assert "not published" in result.message.lower()

    def test_validate_nonexistent(self, db):
        """Test validating nonexistent product."""
        result = CatalogService.validate("NONEXISTENT")
        assert result.valid is False
        assert result.error_code == "not_found"


class TestCatalogSearch:
    """Tests for CatalogService.search()."""

    def test_search_by_name(self, db):
        """Test search by name."""
        product = Product.objects.create(sku="BAGUETE", name="Baguete")
        Product.objects.create(sku="CROISSANT", name="Croissant")

        results = CatalogService.search(query="Baguete")
        assert len(results) == 1
        assert results[0] == product

    def test_search_by_sku(self, db):
        """Test search by SKU."""
        product = Product.objects.create(sku="BAGUETE", name="Baguete")

        results = CatalogService.search(query="BAGUETE")
        assert len(results) == 1
        assert results[0] == product

    def test_search_excludes_unpublished(self, db):
        """Test search excludes unpublished by default."""
        Product.objects.create(sku="BAGUETE", name="Baguete")
        Product.objects.create(sku="HIDDEN-001", name="Hidden", is_published=False)

        results = CatalogService.search(only_published=True)
        skus = [p.sku for p in results]
        assert "BAGUETE" in skus
        assert "HIDDEN-001" not in skus

    def test_search_limit(self, db):
        """Test search limit."""
        for i in range(10):
            Product.objects.create(
                sku=f"TEST-{i:03d}",
                name=f"Test Product {i}",
                base_price_q=100,
            )

        results = CatalogService.search(limit=5)
        assert len(results) <= 5


class TestCatalogAvailability:
    """Tests for CatalogService listing semantics."""

    def test_get_listed_products(self, db):
        """Listed means structurally present in the listing."""
        listing = Listing.objects.create(ref="shop", name="Shop")
        product1 = Product.objects.create(sku="P1", name="Product 1")
        product2 = Product.objects.create(sku="P2", name="Product 2", is_sellable=False)

        ListingItem.objects.create(listing=listing, product=product1, price_q=500)
        ListingItem.objects.create(listing=listing, product=product2, price_q=600)

        listed = CatalogService.get_listed_products("shop")
        skus = [p.sku for p in listed]
        assert "P1" in skus
        assert "P2" in skus

    def test_is_product_listed(self, db):
        """Listed means linked to the listing, nothing else."""
        listing = Listing.objects.create(ref="shop", name="Shop")
        product = Product.objects.create(sku="P1", name="Product 1")
        ListingItem.objects.create(listing=listing, product=product, price_q=500)

        assert CatalogService.is_product_listed(product, "shop") is True
        assert CatalogService.is_product_listed(product, "nonexistent") is False

    def test_published_products_exclude_hidden_listing_items(self, db):
        """Published means visible in the listing."""
        listing = Listing.objects.create(ref="shop", name="Shop")
        product = Product.objects.create(sku="P1", name="Product 1")
        ListingItem.objects.create(
            listing=listing, product=product, price_q=500,
            is_published=False,  # Unpublished in this listing
        )

        assert CatalogService.is_product_listed(product, "shop") is True
        assert CatalogService.is_product_published(product, "shop") is False
        assert product not in CatalogService.get_published_products("shop")

    def test_sellable_products_exclude_paused_listing_items(self, db):
        """Sellable means strategically purchasable in the listing."""
        listing = Listing.objects.create(ref="shop", name="Shop")
        product = Product.objects.create(sku="P1", name="Product 1")
        ListingItem.objects.create(
            listing=listing, product=product, price_q=500,
            is_published=True,
            is_sellable=False,
        )

        assert CatalogService.is_product_listed(product, "shop") is True
        assert CatalogService.is_product_sellable(product, "shop") is False
        assert product not in CatalogService.get_sellable_products("shop")

    def test_expired_listing_excludes_products(self, db):
        """Expired listing should not return products as available."""
        from datetime import date, timedelta

        listing = Listing.objects.create(
            ref="promo-old",
            name="Old Promo",
            is_active=True,
            valid_until=date.today() - timedelta(days=1),
        )
        product = Product.objects.create(sku="EXP-1", name="Product")
        ListingItem.objects.create(listing=listing, product=product, price_q=500)

        listed = CatalogService.get_listed_products("promo-old")
        assert product not in listed

        assert CatalogService.is_product_listed(product, "promo-old") is False

    def test_future_listing_excludes_products(self, db):
        """Listing not yet started should not return products as available."""
        from datetime import date, timedelta

        listing = Listing.objects.create(
            ref="promo-future",
            name="Future Promo",
            is_active=True,
            valid_from=date.today() + timedelta(days=1),
        )
        product = Product.objects.create(sku="FUT-1", name="Product")
        ListingItem.objects.create(listing=listing, product=product, price_q=500)

        listed = CatalogService.get_listed_products("promo-future")
        assert product not in listed

        assert CatalogService.is_product_listed(product, "promo-future") is False

    def test_valid_listing_with_dates_includes_products(self, db):
        """Listing within valid date range should return products."""
        from datetime import date, timedelta

        listing = Listing.objects.create(
            ref="promo-active",
            name="Active Promo",
            is_active=True,
            valid_from=date.today() - timedelta(days=1),
            valid_until=date.today() + timedelta(days=1),
        )
        product = Product.objects.create(sku="VAL-1", name="Product")
        ListingItem.objects.create(listing=listing, product=product, price_q=500)

        listed = CatalogService.get_listed_products("promo-active")
        assert product in listed

        assert CatalogService.is_product_listed(product, "promo-active") is True

    def test_listing_without_dates_includes_products(self, db):
        """Listing without date constraints (null) should return products."""
        listing = Listing.objects.create(
            ref="evergreen",
            name="Evergreen",
            is_active=True,
        )
        product = Product.objects.create(sku="EVR-1", name="Product")
        ListingItem.objects.create(listing=listing, product=product, price_q=500)

        listed = CatalogService.get_listed_products("evergreen")
        assert product in listed

        assert CatalogService.is_product_listed(product, "evergreen") is True


# ═══════════════════════════════════════════════════════════════════
# 4.1 — Pricing by channel (complete flow)
# ═══════════════════════════════════════════════════════════════════


class TestCatalogPriceChannel:
    """Full pricing flow with channel/listing support."""

    def test_base_price_without_channel(self, db):
        """Base price returned when no channel specified."""
        Product.objects.create(sku="CH-1", name="Product", base_price_q=500)
        assert CatalogService.price("CH-1") == 500

    def test_price_with_channel_and_listing_item(self, db):
        """Channel-specific price overrides base price."""
        p = Product.objects.create(sku="CH-2", name="Product", base_price_q=500)
        listing = Listing.objects.create(ref="ifood", name="iFood")
        ListingItem.objects.create(listing=listing, product=p, price_q=700)

        assert CatalogService.price("CH-2", channel="ifood") == 700

    def test_price_with_channel_no_item_fallback(self, db):
        """Channel exists but product not listed — fallback to base."""
        Product.objects.create(sku="CH-3", name="Product", base_price_q=500)
        Listing.objects.create(ref="ifood", name="iFood")

        assert CatalogService.price("CH-3", channel="ifood") == 500

    def test_price_with_nonexistent_channel_fallback(self, db):
        """Nonexistent channel — fallback to base."""
        Product.objects.create(sku="CH-4", name="Product", base_price_q=500)
        assert CatalogService.price("CH-4", channel="doesnt-exist") == 500

    def test_price_with_tiered_pricing(self, db):
        """min_qty tiers select highest qualifying tier."""
        p = Product.objects.create(sku="CH-5", name="Product", base_price_q=500)
        listing = Listing.objects.create(ref="atacado", name="Wholesale")
        ListingItem.objects.create(listing=listing, product=p, price_q=500, min_qty=Decimal("1"))
        ListingItem.objects.create(listing=listing, product=p, price_q=400, min_qty=Decimal("10"))
        ListingItem.objects.create(listing=listing, product=p, price_q=350, min_qty=Decimal("50"))

        # qty=5 → tier min_qty=1 → price 500
        assert CatalogService.price("CH-5", qty=Decimal("5"), channel="atacado") == 2500

        # qty=10 → tier min_qty=10 → price 400
        assert CatalogService.price("CH-5", qty=Decimal("10"), channel="atacado") == 4000

        # qty=100 → tier min_qty=50 → price 350
        assert CatalogService.price("CH-5", qty=Decimal("100"), channel="atacado") == 35000

    def test_price_with_expired_listing(self, db):
        """Expired listing falls back to base price."""
        from datetime import date, timedelta

        p = Product.objects.create(sku="CH-6", name="Product", base_price_q=500)
        listing = Listing.objects.create(
            ref="promo",
            name="Promo",
            valid_until=date.today() - timedelta(days=1),
        )
        ListingItem.objects.create(listing=listing, product=p, price_q=300)

        assert CatalogService.price("CH-6", channel="promo") == 500


# ═══════════════════════════════════════════════════════════════════
# 4.1b — unit_price cascade (min_qty tiers)
# ═══════════════════════════════════════════════════════════════════


class TestCatalogUnitPriceCascade:
    """Tests for CatalogService.unit_price() with min_qty cascading."""

    def test_unit_price_no_listing_returns_base(self, db):
        """Without a listing, unit_price returns base_price_q."""
        Product.objects.create(sku="UP-1", name="Product", base_price_q=500)
        assert CatalogService.unit_price("UP-1") == 500

    def test_unit_price_single_tier(self, db):
        """Single ListingItem (default min_qty=1) returns its price."""
        p = Product.objects.create(sku="UP-2", name="Product", base_price_q=500)
        listing = Listing.objects.create(ref="shop", name="Shop")
        ListingItem.objects.create(listing=listing, product=p, price_q=450)

        assert CatalogService.unit_price("UP-2", channel="shop") == 450

    def test_unit_price_cascade_three_tiers(self, db):
        """Three tiers: 1 un = R$5, 3+ = R$4, 10+ = R$3.50."""
        p = Product.objects.create(sku="UP-3", name="Product", base_price_q=600)
        listing = Listing.objects.create(ref="loja", name="Loja")
        ListingItem.objects.create(listing=listing, product=p, price_q=500, min_qty=Decimal("1"))
        ListingItem.objects.create(listing=listing, product=p, price_q=400, min_qty=Decimal("3"))
        ListingItem.objects.create(listing=listing, product=p, price_q=350, min_qty=Decimal("10"))

        # qty=1 → tier min_qty=1 → unit R$5.00
        assert CatalogService.unit_price("UP-3", qty=Decimal("1"), channel="loja") == 500

        # qty=2 → tier min_qty=1 → unit R$5.00
        assert CatalogService.unit_price("UP-3", qty=Decimal("2"), channel="loja") == 500

        # qty=3 → tier min_qty=3 → unit R$4.00
        assert CatalogService.unit_price("UP-3", qty=Decimal("3"), channel="loja") == 400

        # qty=5 → tier min_qty=3 → unit R$4.00
        assert CatalogService.unit_price("UP-3", qty=Decimal("5"), channel="loja") == 400

        # qty=10 → tier min_qty=10 → unit R$3.50
        assert CatalogService.unit_price("UP-3", qty=Decimal("10"), channel="loja") == 350

        # qty=15 → tier min_qty=10 → unit R$3.50
        assert CatalogService.unit_price("UP-3", qty=Decimal("15"), channel="loja") == 350

    def test_unit_price_qty_below_all_tiers_falls_back(self, db):
        """Qty below all min_qty thresholds falls back to base_price_q."""
        p = Product.objects.create(sku="UP-4", name="Product", base_price_q=600)
        listing = Listing.objects.create(ref="atacado", name="Atacado")
        # Only tier starts at min_qty=5
        ListingItem.objects.create(listing=listing, product=p, price_q=400, min_qty=Decimal("5"))
        ListingItem.objects.create(listing=listing, product=p, price_q=350, min_qty=Decimal("10"))

        # qty=2 → no tier qualifies → fallback to base 600
        assert CatalogService.unit_price("UP-4", qty=Decimal("2"), channel="atacado") == 600

    def test_price_total_uses_cascaded_unit(self, db):
        """CatalogService.price() computes total = unit_price * qty."""
        p = Product.objects.create(sku="UP-5", name="Product", base_price_q=600)
        listing = Listing.objects.create(ref="loja", name="Loja")
        ListingItem.objects.create(listing=listing, product=p, price_q=500, min_qty=Decimal("1"))
        ListingItem.objects.create(listing=listing, product=p, price_q=400, min_qty=Decimal("3"))

        # qty=5 → tier 3+ → unit=400 → total=2000
        assert CatalogService.price("UP-5", qty=Decimal("5"), channel="loja") == 2000

    def test_unit_price_nonexistent_product(self, db):
        """unit_price raises CatalogError for unknown SKU."""
        with pytest.raises(CatalogError) as exc:
            CatalogService.unit_price("NONEXISTENT")
        assert exc.value.code == "SKU_NOT_FOUND"

    def test_unit_price_invalid_quantity(self, db):
        """unit_price raises CatalogError for qty <= 0."""
        Product.objects.create(sku="UP-6", name="Product", base_price_q=500)
        with pytest.raises(CatalogError) as exc:
            CatalogService.unit_price("UP-6", qty=Decimal("0"))
        assert exc.value.code == "INVALID_QUANTITY"

    def test_unit_price_no_channel_with_qty(self, db):
        """Without channel, unit_price always returns base_price_q regardless of qty."""
        Product.objects.create(sku="UP-7", name="Product", base_price_q=500)
        assert CatalogService.unit_price("UP-7", qty=Decimal("100")) == 500


# ═══════════════════════════════════════════════════════════════════
# 4.2 — Search with combined filters
# ═══════════════════════════════════════════════════════════════════


class TestCatalogSearchFilters:
    """Search with collection and keyword combinations."""

    def test_search_by_collection(self, db):
        """Filter by collection slug."""
        coll = Collection.objects.create(ref="doces", name="Doces")
        p1 = Product.objects.create(sku="BOLO", name="Bolo")
        Product.objects.create(sku="PAO", name="Pao")
        CollectionItem.objects.create(collection=coll, product=p1, is_primary=True)

        results = CatalogService.search(collection="doces")
        assert len(results) == 1
        assert results[0].sku == "BOLO"

    def test_search_by_keywords(self, db):
        """Filter by keyword tags."""
        p1 = Product.objects.create(sku="BOLO-CHOC", name="Bolo de Chocolate")
        p1.keywords.add("chocolate", "doce")
        p2 = Product.objects.create(sku="PAO-FRANCES", name="Pao Frances")
        p2.keywords.add("salgado")

        results = CatalogService.search(keywords=["chocolate"])
        skus = [r.sku for r in results]
        assert "BOLO-CHOC" in skus
        assert "PAO-FRANCES" not in skus

    def test_search_query_and_collection(self, db):
        """Combined query text + collection filter."""
        from shopman.offerman.models import Collection, CollectionItem

        coll = Collection.objects.create(ref="paes", name="Paes")
        p1 = Product.objects.create(sku="PAO-INT", name="Pao Integral")
        p2 = Product.objects.create(sku="PAO-FR", name="Pao Frances")
        p3 = Product.objects.create(sku="BOLO-INT", name="Bolo Integral")
        CollectionItem.objects.create(collection=coll, product=p1)
        CollectionItem.objects.create(collection=coll, product=p2)
        # p3 NOT in collection

        results = CatalogService.search(query="Integral", collection="paes")
        skus = [r.sku for r in results]
        assert "PAO-INT" in skus
        assert "PAO-FR" not in skus  # Doesn't match query
        assert "BOLO-INT" not in skus  # Not in collection


# ═══════════════════════════════════════════════════════════════════
# 4.3 — Adapters
# ═══════════════════════════════════════════════════════════════════


class TestCatalogBackendAdapter:
    """CatalogBackend integration."""

    def test_get_product_returns_info(self, db):
        """get_product returns correct ProductInfo fields."""
        from shopman.offerman.adapters.catalog_backend import OffermanCatalogBackend

        p = Product.objects.create(
            sku="ADAPT-1", name="Adapter Test", base_price_q=999,
            unit="kg", long_description="Test description",
        )
        coll = Collection.objects.create(ref="test-cat", name="Test Cat")
        CollectionItem.objects.create(collection=coll, product=p, is_primary=True)

        backend = OffermanCatalogBackend()
        info = backend.get_product("ADAPT-1")

        assert info is not None
        assert info.sku == "ADAPT-1"
        assert info.name == "Adapter Test"
        assert info.unit == "kg"
        assert info.base_price_q == 999
        assert info.category == "test-cat"
        assert info.is_bundle is False

    def test_get_product_not_found(self, db):
        """get_product returns None for unknown SKU."""
        from shopman.offerman.adapters.catalog_backend import OffermanCatalogBackend

        backend = OffermanCatalogBackend()
        assert backend.get_product("NONEXISTENT") is None

    def test_get_price_fractional_rounding(self, db):
        """get_price rounds correctly for fractional qty."""
        from shopman.offerman.adapters.catalog_backend import OffermanCatalogBackend
        from unittest.mock import patch

        backend = OffermanCatalogBackend()

        with patch("shopman.offerman.adapters.catalog_backend.CatalogService.price", return_value=1001):
            result = backend.get_price("ANY", qty=Decimal("3"))

        assert result.unit_price_q == 334  # round(1001/3)
        assert result.total_price_q == 1001

    def test_expand_bundle_returns_components(self, db):
        """expand_bundle returns BundleComponent list."""
        from shopman.offerman.adapters.catalog_backend import OffermanCatalogBackend
        from shopman.offerman.models import ProductComponent

        combo = Product.objects.create(sku="COMBO-A", name="Combo A", base_price_q=1000)
        comp1 = Product.objects.create(sku="ITEM-1", name="Item 1", base_price_q=500)
        comp2 = Product.objects.create(sku="ITEM-2", name="Item 2", base_price_q=600)
        ProductComponent.objects.create(parent=combo, component=comp1, qty=Decimal("2"))
        ProductComponent.objects.create(parent=combo, component=comp2, qty=Decimal("1"))

        backend = OffermanCatalogBackend()
        result = backend.expand_bundle("COMBO-A")

        assert len(result) == 2
        skus = [r.sku for r in result]
        assert "ITEM-1" in skus
        assert "ITEM-2" in skus

    def test_expand_bundle_non_bundle_returns_empty(self, db):
        """expand_bundle on non-bundle returns empty list."""
        from shopman.offerman.adapters.catalog_backend import OffermanCatalogBackend

        Product.objects.create(sku="SINGLE", name="Single", base_price_q=500)
        backend = OffermanCatalogBackend()
        result = backend.expand_bundle("SINGLE")
        assert result == []


# ═══════════════════════════════════════════════════════════════════
# 4.4 — Suggestions
# ═══════════════════════════════════════════════════════════════════


class TestSuggestions:
    """find_alternatives and find_similar tests."""

    def test_find_alternatives_with_keywords(self, db):
        """find_alternatives returns products with common keywords."""
        from shopman.offerman.contrib.suggestions.suggestions import find_alternatives
        from shopman.offerman.models import Collection, CollectionItem

        coll = Collection.objects.create(ref="paes", name="Paes")
        p1 = Product.objects.create(sku="PAO-INT", name="Pao Integral", base_price_q=400)
        p1.keywords.add("integral", "pao")
        CollectionItem.objects.create(collection=coll, product=p1, is_primary=True)

        p2 = Product.objects.create(sku="PAO-7G", name="Pao 7 Graos", base_price_q=500)
        p2.keywords.add("integral", "graos")
        CollectionItem.objects.create(collection=coll, product=p2, is_primary=True)

        p3 = Product.objects.create(sku="BOLO", name="Bolo", base_price_q=1000)
        p3.keywords.add("doce")
        CollectionItem.objects.create(collection=coll, product=p3, is_primary=True)

        alternatives = find_alternatives("PAO-INT")
        skus = [a.sku for a in alternatives]
        assert "PAO-7G" in skus  # Shares 'integral' keyword
        assert "BOLO" not in skus  # No common keyword

    def test_find_alternatives_no_keywords(self, db):
        """find_alternatives returns empty when product has no keywords."""
        from shopman.offerman.contrib.suggestions.suggestions import find_alternatives

        Product.objects.create(sku="NAKED", name="No Keywords", base_price_q=100)
        assert find_alternatives("NAKED") == []

    def test_find_alternatives_nonexistent(self, db):
        """find_alternatives returns empty for unknown SKU."""
        from shopman.offerman.contrib.suggestions.suggestions import find_alternatives

        assert find_alternatives("GHOST") == []

    def test_find_similar_same_collection(self, db):
        """find_similar returns products from same collection with keywords."""
        from shopman.offerman.contrib.suggestions.suggestions import find_similar
        from shopman.offerman.models import Collection, CollectionItem

        coll = Collection.objects.create(ref="paes", name="Paes")
        p1 = Product.objects.create(sku="SIM-1", name="Product 1", base_price_q=400)
        p1.keywords.add("artesanal")
        CollectionItem.objects.create(collection=coll, product=p1, is_primary=True)

        p2 = Product.objects.create(sku="SIM-2", name="Product 2", base_price_q=500)
        p2.keywords.add("artesanal")
        CollectionItem.objects.create(collection=coll, product=p2, is_primary=True)

        similar = find_similar("SIM-1")
        skus = [s.sku for s in similar]
        assert "SIM-2" in skus
