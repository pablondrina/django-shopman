"""
H21 — Offerman hardening tests.

Tests for:
- CatalogBackend.get_price() with fractional division
- ProductComponent circular reference via save()
- Listing with channel override
- Product.margin_percent with base_price=0 (ZeroDivisionError)
- Collection.get_descendants() deep hierarchy
"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError

from shopman.offerman.models import (
    Product,
    Collection,
    CollectionItem,
    ProductComponent,
    Listing,
    ListingItem,
)


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def collection_h21(db):
    return Collection.objects.create(ref="h21-test", name="Test")


@pytest.fixture
def product_a(db, collection_h21):
    p = Product.objects.create(
        sku="H21-A",
        name="Product A",
        base_price_q=1000,
        unit="un",
        is_sellable=True,
    )
    CollectionItem.objects.create(collection=collection_h21, product=p, is_primary=True)
    return p


@pytest.fixture
def product_b(db, collection_h21):
    p = Product.objects.create(
        sku="H21-B",
        name="Product B",
        base_price_q=2000,
        unit="un",
        is_sellable=True,
    )
    CollectionItem.objects.create(collection=collection_h21, product=p, is_primary=True)
    return p


@pytest.fixture
def product_c(db, collection_h21):
    p = Product.objects.create(
        sku="H21-C",
        name="Product C",
        base_price_q=500,
        unit="un",
        is_sellable=True,
    )
    CollectionItem.objects.create(collection=collection_h21, product=p, is_primary=True)
    return p


@pytest.fixture
def product_zero_price(db, collection_h21):
    p = Product.objects.create(
        sku="H21-ZERO",
        name="Free Sample",
        base_price_q=0,
        unit="un",
        is_sellable=True,
    )
    CollectionItem.objects.create(collection=collection_h21, product=p, is_primary=True)
    return p


# ═══════════════════════════════════════════════════════════════════
# CatalogBackend.get_price() with fractional division
# ═══════════════════════════════════════════════════════════════════


class TestCatalogBackendFractionalPrice:
    """get_price() must use round() not // for unit price."""

    def test_1001_divided_by_3_rounds_correctly(self):
        """R$10.01 / 3 = 334 centavos (round), not 333 (//)."""
        from shopman.offerman.adapters.catalog_backend import OffermanCatalogBackend

        backend = OffermanCatalogBackend()

        with patch("shopman.offerman.adapters.catalog_backend.CatalogService.price", return_value=1001):
            result = backend.get_price("ANY-SKU", qty=Decimal("3"))

        assert result.unit_price_q == 334  # round(1001/3) = 334

    def test_500_divided_by_3_rounds_correctly(self):
        """R$5.00 / 3 = 167 centavos (round), not 166 (//)."""
        from shopman.offerman.adapters.catalog_backend import OffermanCatalogBackend

        backend = OffermanCatalogBackend()

        with patch("shopman.offerman.adapters.catalog_backend.CatalogService.price", return_value=500):
            result = backend.get_price("ANY-SKU", qty=Decimal("3"))

        assert result.unit_price_q == 167

    def test_qty_zero_returns_total(self):
        """qty=0 returns total_price_q unchanged."""
        from shopman.offerman.adapters.catalog_backend import OffermanCatalogBackend

        backend = OffermanCatalogBackend()

        with patch("shopman.offerman.adapters.catalog_backend.CatalogService.price", return_value=999):
            result = backend.get_price("ANY-SKU", qty=Decimal("0"))

        assert result.unit_price_q == 999

    def test_exact_division(self):
        """R$10.00 / 2 = 500 centavos (exact)."""
        from shopman.offerman.adapters.catalog_backend import OffermanCatalogBackend

        backend = OffermanCatalogBackend()

        with patch("shopman.offerman.adapters.catalog_backend.CatalogService.price", return_value=1000):
            result = backend.get_price("ANY-SKU", qty=Decimal("2"))

        assert result.unit_price_q == 500


# ═══════════════════════════════════════════════════════════════════
# ProductComponent circular reference via save()
# ═══════════════════════════════════════════════════════════════════


class TestProductComponentCircularReference:
    """ProductComponent.save() calls full_clean() which detects circular refs."""

    def test_self_reference_rejected(self, product_a):
        """Product cannot be component of itself."""
        with pytest.raises(ValidationError, match="component of itself"):
            ProductComponent.objects.create(
                parent=product_a,
                component=product_a,
                qty=Decimal("1"),
            )

    def test_direct_circular_reference_rejected(self, product_a, product_b):
        """A->B and B->A is circular."""
        ProductComponent.objects.create(
            parent=product_a,
            component=product_b,
            qty=Decimal("2"),
        )

        with pytest.raises(ValidationError, match="Circular"):
            ProductComponent.objects.create(
                parent=product_b,
                component=product_a,
                qty=Decimal("1"),
            )

    def test_indirect_circular_reference_rejected(self, product_a, product_b, product_c):
        """A->B->C and C->A is circular."""
        ProductComponent.objects.create(
            parent=product_a,
            component=product_b,
            qty=Decimal("1"),
        )
        ProductComponent.objects.create(
            parent=product_b,
            component=product_c,
            qty=Decimal("1"),
        )

        with pytest.raises(ValidationError, match="Circular"):
            ProductComponent.objects.create(
                parent=product_c,
                component=product_a,
                qty=Decimal("1"),
            )

    def test_valid_component_accepted(self, product_a, product_b):
        """Non-circular component is accepted."""
        comp = ProductComponent.objects.create(
            parent=product_a,
            component=product_b,
            qty=Decimal("3"),
        )
        assert comp.pk is not None
        assert comp.qty == Decimal("3")


# ═══════════════════════════════════════════════════════════════════
# Listing with channel override
# ═══════════════════════════════════════════════════════════════════


class TestListingChannelOverride:
    """Listing items override base price for specific channels."""

    def test_listing_overrides_base_price(self, product_a):
        """Listing item price takes precedence over base_price_q."""
        listing = Listing.objects.create(
            ref="ifood",
            name="iFood",
            is_active=True,
            priority=10,
        )
        ListingItem.objects.create(
            listing=listing,
            product=product_a,
            price_q=1500,  # 50% more than base (1000)
        )

        from shopman.offerman.service import CatalogService

        price = CatalogService.price(product_a.sku, channel="ifood")
        assert price == 1500

    def test_fallback_to_base_price_without_channel(self, product_a):
        """Without channel, returns base_price_q."""
        from shopman.offerman.service import CatalogService

        price = CatalogService.price(product_a.sku)
        assert price == product_a.base_price_q


# ═══════════════════════════════════════════════════════════════════
# Arithmetic rounding (2.1, 2.2, 2.3)
# ═══════════════════════════════════════════════════════════════════


class TestArithmeticRounding:
    """CatalogService.price() and base_price setter must round, not truncate."""

    def test_price_with_fractional_qty_rounds_up(self, product_a):
        """qty=1.5 * price_q=333 → 500, not 499."""
        from shopman.offerman.service import CatalogService

        product_a.base_price_q = 333
        product_a.save()

        price = CatalogService.price(product_a.sku, qty=Decimal("1.5"))
        assert price == 500  # round(333 * 1.5) = 500, not int(499.5) = 499

    def test_price_with_fractional_qty_rounds_half(self, product_a):
        """qty=0.5 * price_q=999 → 500, not 499."""
        from shopman.offerman.service import CatalogService

        product_a.base_price_q = 999
        product_a.save()

        price = CatalogService.price(product_a.sku, qty=Decimal("0.5"))
        assert price == 500  # round(999 * 0.5) = 500

    def test_base_price_setter_rounds_correctly(self, db):
        """base_price setter must round Decimal('9.999') → 1000, not 999."""
        p = Product.objects.create(sku="ROUND-TEST", name="Round Test")
        p.base_price = Decimal("9.999")
        assert p.base_price_q == 1000  # round(999.9) = 1000, not int(999.9) = 999

    def test_base_price_setter_exact(self, db):
        """base_price setter exact value."""
        p = Product.objects.create(sku="EXACT-TEST", name="Exact Test")
        p.base_price = Decimal("7.50")
        assert p.base_price_q == 750


# ═══════════════════════════════════════════════════════════════════
# Product.margin_percent with base_price=0
# ═══════════════════════════════════════════════════════════════════


class TestProductMarginZeroPrice:
    """Product with base_price=0 must not raise ZeroDivisionError."""

    def test_zero_price_product_exists(self, product_zero_price):
        """Product with base_price_q=0 can be created."""
        assert product_zero_price.base_price_q == 0

    def test_zero_price_with_cost_backend(self, product_zero_price):
        """Product with base_price=0 and CostBackend cost handles gracefully."""
        from unittest.mock import MagicMock
        import shopman.offerman.conf as conf

        mock_backend = MagicMock()
        mock_backend.get_cost.return_value = 500
        original = conf._cost_backend_instance
        conf._cost_backend_instance = mock_backend

        try:
            # base_price property should return Decimal
            assert product_zero_price.base_price == Decimal("0")
            # margin_percent should return None (base_price=0, avoids ZeroDivision)
            assert product_zero_price.margin_percent is None
        finally:
            conf._cost_backend_instance = original


# ═══════════════════════════════════════════════════════════════════
# Collection.get_descendants() deep hierarchy
# ═══════════════════════════════════════════════════════════════════


class TestCollectionDeepHierarchy:
    """Collection hierarchy operations with deep nesting."""

    def test_get_descendants_three_levels(self, db):
        """Three-level hierarchy returns all descendants."""
        root = Collection.objects.create(ref="root", name="Root")
        child1 = Collection.objects.create(ref="child1", name="Child 1", parent=root)
        child2 = Collection.objects.create(ref="child2", name="Child 2", parent=root)
        grandchild1 = Collection.objects.create(
            ref="grandchild1", name="Grandchild 1", parent=child1
        )
        grandchild2 = Collection.objects.create(
            ref="grandchild2", name="Grandchild 2", parent=child1
        )

        descendants = root.get_descendants()
        desc_ids = {d.pk for d in descendants}

        assert child1.pk in desc_ids
        assert child2.pk in desc_ids
        assert grandchild1.pk in desc_ids
        assert grandchild2.pk in desc_ids
        assert root.pk not in desc_ids
        assert len(descendants) == 4

    def test_full_path_three_levels(self, db):
        """full_path shows complete hierarchy."""
        root = Collection.objects.create(ref="padaria", name="Padaria")
        sub = Collection.objects.create(ref="paes", name="Paes", parent=root)
        leaf = Collection.objects.create(ref="integrais", name="Integrais", parent=sub)

        assert leaf.full_path == "Padaria > Paes > Integrais"
        assert leaf.depth == 2

    def test_leaf_has_no_descendants(self, db):
        """Leaf collection returns empty list of descendants."""
        leaf = Collection.objects.create(ref="leaf", name="Leaf")
        assert leaf.get_descendants() == []

    def test_get_ancestors(self, db):
        """get_ancestors returns path from root to parent."""
        root = Collection.objects.create(ref="a-root", name="Root")
        mid = Collection.objects.create(ref="a-mid", name="Mid", parent=root)
        leaf = Collection.objects.create(ref="a-leaf", name="Leaf", parent=mid)

        ancestors = leaf.get_ancestors()
        assert len(ancestors) == 2
        assert ancestors[0].pk == root.pk
        assert ancestors[1].pk == mid.pk
