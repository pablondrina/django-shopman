"""
Tests for Offerman V2 improvements.

Tests:
- C1: CatalogError inherits from BaseError
- C2: format_money()
- O1: Signals (product_created, price_changed)
- O2: CostBackend Protocol
- O3: get_descendants() with settings max_depth
- O4: Suggestions scoring
- Micro-PIM: shelf_life_days, is_perishable, production_cycle_hours
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from shopman.offerman.exceptions import CatalogError
from shopman.offerman.models import (
    Collection,
    CollectionItem,
    Listing,
    ListingItem,
    Product,
)

pytestmark = pytest.mark.django_db


# ═══════════════════════════════════════════════════════════════════
# C1: CatalogError inherits from BaseError
# ═══════════════════════════════════════════════════════════════════


class TestCatalogErrorBaseError:
    """CatalogError must inherit from BaseError."""

    def test_inherits_from_base_error(self):
        from shopman.utils.exceptions import BaseError

        assert issubclass(CatalogError, BaseError)

    def test_default_messages(self):
        err = CatalogError("SKU_NOT_FOUND")
        assert err.message == "SKU not found"
        assert err.code == "SKU_NOT_FOUND"

    def test_custom_message(self):
        err = CatalogError("SKU_NOT_FOUND", message="Custom message")
        assert err.message == "Custom message"

    def test_as_dict(self):
        err = CatalogError("SKU_NOT_FOUND", sku="XYZ")
        d = err.as_dict()
        assert d["code"] == "SKU_NOT_FOUND"
        assert d["data"]["sku"] == "XYZ"

    def test_sku_property(self):
        err = CatalogError("SKU_NOT_FOUND", sku="ABC")
        assert err.sku == "ABC"

    def test_sku_property_missing(self):
        err = CatalogError("INVALID_QUANTITY")
        assert err.sku is None


# ═══════════════════════════════════════════════════════════════════
# C2: format_money()
# ═══════════════════════════════════════════════════════════════════


class TestFormatMoney:
    """format_money() formats centavos as currency string."""

    def test_basic(self):
        from shopman.utils.monetary import format_money

        assert format_money(1250) == "12,50"

    def test_zero(self):
        from shopman.utils.monetary import format_money

        assert format_money(0) == "0,00"

    def test_small_value(self):
        from shopman.utils.monetary import format_money

        assert format_money(5) == "0,05"

    def test_negative(self):
        from shopman.utils.monetary import format_money

        assert format_money(-1250) == "-12,50"

    def test_large_value(self):
        from shopman.utils.monetary import format_money

        assert format_money(1000000) == "10.000,00"


# ═══════════════════════════════════════════════════════════════════
# O1: Signals — product_created and price_changed
# ═══════════════════════════════════════════════════════════════════


class TestProductCreatedSignal:
    """product_created signal emitted on new Product creation."""

    def test_signal_emitted_on_create(self, db):
        from shopman.offerman.signals import product_created

        received = []

        def handler(sender, instance, sku, **kwargs):
            received.append({"sender": sender, "sku": sku, "instance": instance})

        product_created.connect(handler)
        try:
            product = Product.objects.create(sku="SIG-001", name="Signal Test")
            assert len(received) == 1
            assert received[0]["sku"] == "SIG-001"
            assert received[0]["instance"] == product
        finally:
            product_created.disconnect(handler)

    def test_signal_not_emitted_on_update(self, db):
        from shopman.offerman.signals import product_created

        received = []

        def handler(sender, instance, sku, **kwargs):
            received.append(sku)

        product = Product.objects.create(sku="SIG-002", name="Signal Test")

        product_created.connect(handler)
        try:
            received.clear()
            product.name = "Updated Name"
            product.save()
            assert len(received) == 0  # No signal on update
        finally:
            product_created.disconnect(handler)


class TestPriceChangedSignal:
    """price_changed signal emitted when ListingItem price changes."""

    def test_signal_emitted_on_price_change(self, db):
        from shopman.offerman.signals import price_changed

        listing = Listing.objects.create(ref="sig-listing", name="Test")
        product = Product.objects.create(sku="SIG-P1", name="Product")
        item = ListingItem.objects.create(listing=listing, product=product, price_q=500)

        received = []

        def handler(sender, instance, listing_ref, sku, old_price_q, new_price_q, **kwargs):
            received.append({
                "listing_ref": listing_ref,
                "sku": sku,
                "old_price_q": old_price_q,
                "new_price_q": new_price_q,
            })

        price_changed.connect(handler)
        try:
            item.price_q = 600
            item.save()
            assert len(received) == 1
            assert received[0]["old_price_q"] == 500
            assert received[0]["new_price_q"] == 600
            assert received[0]["sku"] == "SIG-P1"
            assert received[0]["listing_ref"] == "sig-listing"
        finally:
            price_changed.disconnect(handler)

    def test_signal_not_emitted_when_price_unchanged(self, db):
        from shopman.offerman.signals import price_changed

        listing = Listing.objects.create(ref="sig-listing2", name="Test")
        product = Product.objects.create(sku="SIG-P2", name="Product")
        item = ListingItem.objects.create(listing=listing, product=product, price_q=500)

        received = []

        def handler(sender, **kwargs):
            received.append(True)

        price_changed.connect(handler)
        try:
            # Save without changing price
            item.is_published = False
            item.save()
            assert len(received) == 0
        finally:
            price_changed.disconnect(handler)

    def test_signal_not_emitted_on_create(self, db):
        from shopman.offerman.signals import price_changed

        listing = Listing.objects.create(ref="sig-listing3", name="Test")
        product = Product.objects.create(sku="SIG-P3", name="Product")

        received = []

        def handler(sender, **kwargs):
            received.append(True)

        price_changed.connect(handler)
        try:
            ListingItem.objects.create(listing=listing, product=product, price_q=500)
            assert len(received) == 0  # No signal on initial creation
        finally:
            price_changed.disconnect(handler)


# ═══════════════════════════════════════════════════════════════════
# O2: CostBackend Protocol
# ═══════════════════════════════════════════════════════════════════


class TestCostBackendProtocol:
    """CostBackend Protocol for production cost."""

    def test_protocol_definition(self):
        from shopman.offerman.protocols import CostBackend

        class MockCostBackend:
            def get_cost(self, sku: str) -> int | None:
                return 700

        assert isinstance(MockCostBackend(), CostBackend)

    def test_reference_cost_q_with_backend(self, db):
        import shopman.offerman.conf as conf

        product = Product.objects.create(sku="COST-1", name="Test", base_price_q=1000)

        mock_backend = MagicMock()
        mock_backend.get_cost.return_value = 700
        original = conf._cost_backend_instance
        conf._cost_backend_instance = mock_backend

        try:
            assert product.reference_cost_q == 700
            mock_backend.get_cost.assert_called_with("COST-1")
        finally:
            conf._cost_backend_instance = original

    def test_reference_cost_q_without_backend(self, db):
        """Without CostBackend, reference_cost_q returns None."""
        product = Product.objects.create(sku="COST-2", name="Test", base_price_q=1000)
        assert product.reference_cost_q is None

    def test_margin_percent_via_backend(self, db):
        import shopman.offerman.conf as conf

        product = Product.objects.create(sku="COST-3", name="Test", base_price_q=1000)

        mock_backend = MagicMock()
        mock_backend.get_cost.return_value = 600
        original = conf._cost_backend_instance
        conf._cost_backend_instance = mock_backend

        try:
            assert product.margin_percent == Decimal("40.0")
        finally:
            conf._cost_backend_instance = original

    def test_reset_cost_backend(self):
        import shopman.offerman.conf as conf

        conf._cost_backend_instance = "something"
        conf.reset_cost_backend()
        assert conf._cost_backend_instance is None


# ═══════════════════════════════════════════════════════════════════
# O3: get_descendants() with settings max_depth
# ═══════════════════════════════════════════════════════════════════


class TestGetDescendantsMaxDepth:
    """get_descendants() uses settings.MAX_COLLECTION_DEPTH by default."""

    def test_default_uses_settings(self, db):
        """Default max_depth comes from offerman_settings."""
        root = Collection.objects.create(ref="depth-root", name="Root")
        child = Collection.objects.create(ref="depth-child", name="Child", parent=root)

        with patch("shopman.offerman.conf.get_offerman_settings") as mock_settings:
            mock_settings.return_value = MagicMock(MAX_COLLECTION_DEPTH=1)
            descendants = root.get_descendants()
            # Depth limit 1: only direct children
            assert len(descendants) == 1
            assert descendants[0].pk == child.pk

    def test_explicit_max_depth_overrides_settings(self, db):
        root = Collection.objects.create(ref="exp-root", name="Root")
        child = Collection.objects.create(ref="exp-child", name="Child", parent=root)
        grandchild = Collection.objects.create(ref="exp-gchild", name="GChild", parent=child)

        # With max_depth=1, only direct children
        descendants = root.get_descendants(max_depth=1)
        assert len(descendants) == 1

        # With max_depth=2, children + grandchildren
        descendants = root.get_descendants(max_depth=2)
        assert len(descendants) == 2

    def test_get_ancestors_uses_settings(self, db):
        root = Collection.objects.create(ref="anc-root", name="Root")
        child = Collection.objects.create(ref="anc-child", name="Child", parent=root)
        grandchild = Collection.objects.create(ref="anc-gchild", name="GChild", parent=child)

        ancestors = grandchild.get_ancestors()
        assert len(ancestors) == 2


# ═══════════════════════════════════════════════════════════════════
# O4: Suggestions scoring
# ═══════════════════════════════════════════════════════════════════


class TestSuggestionsScoring:
    """Suggestions use scoring: keywords(x3) + collection(x2) + price(x1)."""

    def test_scored_by_keywords(self, db):
        from shopman.offerman.contrib.suggestions.suggestions import find_alternatives

        coll = Collection.objects.create(ref="score-col", name="Test")

        # Reference product
        ref = Product.objects.create(sku="REF-1", name="Reference", base_price_q=1000)
        ref.keywords.add("artesanal", "integral", "pao")
        CollectionItem.objects.create(collection=coll, product=ref, is_primary=True)

        # Candidate A: 2 common keywords
        a = Product.objects.create(sku="CAND-A", name="Candidate A", base_price_q=1000)
        a.keywords.add("artesanal", "integral")
        CollectionItem.objects.create(collection=coll, product=a, is_primary=True)

        # Candidate B: 1 common keyword
        b = Product.objects.create(sku="CAND-B", name="Candidate B", base_price_q=1000)
        b.keywords.add("artesanal")
        CollectionItem.objects.create(collection=coll, product=b, is_primary=True)

        results = find_alternatives("REF-1")
        skus = [r.sku for r in results]
        # A should come before B (more common keywords)
        assert skus.index("CAND-A") < skus.index("CAND-B")

    def test_price_similarity_contributes(self, db):
        from shopman.offerman.contrib.suggestions.suggestions import find_alternatives

        coll = Collection.objects.create(ref="price-col", name="Test")

        ref = Product.objects.create(sku="PRICE-REF", name="Reference", base_price_q=1000)
        ref.keywords.add("doce")
        CollectionItem.objects.create(collection=coll, product=ref, is_primary=True)

        # Candidate A: same keyword, similar price (within ±30%)
        a = Product.objects.create(sku="PRICE-A", name="Similar Price", base_price_q=1100)
        a.keywords.add("doce")
        CollectionItem.objects.create(collection=coll, product=a, is_primary=True)

        # Candidate B: same keyword, very different price
        b = Product.objects.create(sku="PRICE-B", name="Diff Price", base_price_q=5000)
        b.keywords.add("doce")
        CollectionItem.objects.create(collection=coll, product=b, is_primary=True)

        results = find_alternatives("PRICE-REF")
        skus = [r.sku for r in results]
        # A should score higher (price similarity bonus)
        assert skus.index("PRICE-A") < skus.index("PRICE-B")

    def test_find_similar_uses_scoring(self, db):
        from shopman.offerman.contrib.suggestions.suggestions import find_similar

        coll = Collection.objects.create(ref="sim-col", name="Test")

        ref = Product.objects.create(sku="SIM-REF", name="Reference", base_price_q=500)
        ref.keywords.add("cafe", "quente")
        CollectionItem.objects.create(collection=coll, product=ref, is_primary=True)

        a = Product.objects.create(sku="SIM-A", name="Similar A", base_price_q=600)
        a.keywords.add("cafe", "quente")
        CollectionItem.objects.create(collection=coll, product=a, is_primary=True)

        b = Product.objects.create(sku="SIM-B", name="Similar B", base_price_q=400)
        b.keywords.add("cafe")
        CollectionItem.objects.create(collection=coll, product=b, is_primary=True)

        results = find_similar("SIM-REF")
        assert len(results) >= 2
        # A has more keyword matches, should rank higher
        skus = [r.sku for r in results]
        assert skus.index("SIM-A") < skus.index("SIM-B")


# ═══════════════════════════════════════════════════════════════════
# Micro-PIM: shelf_life_days, is_perishable, production_cycle_hours
# ═══════════════════════════════════════════════════════════════════


class TestPerishableFields:
    """Micro-PIM perishable and production fields."""

    def test_perishable_product(self, db):
        product = Product.objects.create(
            sku="PERISHABLE-1",
            name="Fresh Bread",
            shelf_life_days=12,
            production_cycle_hours=4,
        )
        assert product.is_perishable is True
        assert product.shelf_life_days == 12
        assert product.production_cycle_hours == 4

    def test_non_perishable_product(self, db):
        product = Product.objects.create(
            sku="DURABLE-1",
            name="Canned Goods",
        )
        assert product.is_perishable is False
        assert product.shelf_life_days is None
        assert product.production_cycle_hours is None

    def test_zero_shelf_life(self, db):
        """shelf_life_days=0 means immediate consumption, still perishable."""
        product = Product.objects.create(
            sku="IMMEDIATE-1",
            name="Sushi",
            shelf_life_days=0,
        )
        assert product.is_perishable is True
        assert product.shelf_life_days == 0
