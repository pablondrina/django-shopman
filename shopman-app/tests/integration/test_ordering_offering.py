"""
Integration tests: Ordering <-> Offering

Tests the pricing adapters that connect Ordering to Offering's catalog.

Covers:
- SimplePricingBackend (base price from Product)
- ChannelPricingBackend (price list lookup with fallback)
- PricingBackend protocol compliance
"""

from decimal import Decimal

import pytest

from shopman.pricing.adapters.simple import (
    SimplePricingBackend,
    ChannelPricingBackend,
)
from shopman.pricing.protocols import PricingBackend


pytestmark = pytest.mark.django_db


# =============================================================================
# RESOLVERS
# =============================================================================


def get_product_resolver():
    """Create a product resolver function."""
    from shopman.offering.models import Product

    def resolver(sku: str):
        return Product.objects.get(sku=sku)

    return resolver


def get_listing_resolver():
    """Create a listing resolver for listing items."""
    from shopman.offering.models import ListingItem

    def resolver(sku: str, channel_ref: str):
        return ListingItem.objects.get(
            product__sku=sku,
            listing__code=channel_ref,
            listing__is_active=True,
        )

    return resolver


# =============================================================================
# SIMPLE PRICING BACKEND
# =============================================================================


class TestSimplePricingBackend:
    """Tests for SimplePricingBackend (base price only)."""

    @pytest.fixture
    def backend(self):
        """Create SimplePricingBackend instance."""
        return SimplePricingBackend(product_resolver=get_product_resolver())

    def test_get_price_returns_base_price(self, backend, product, channel):
        """Should return product's base_price_q."""
        price = backend.get_price("PAO-FRANCES", channel)

        assert price == 80  # R$ 0.80 in cents

    def test_get_price_ignores_channel(self, backend, product, ifood_channel):
        """SimplePricingBackend ignores channel, always returns base price."""
        price = backend.get_price("PAO-FRANCES", ifood_channel)

        # Still returns base price, not iFood price
        assert price == 80

    def test_get_price_nonexistent_returns_none(self, backend, channel):
        """Nonexistent product should return None."""
        price = backend.get_price("NONEXISTENT-SKU", channel)

        assert price is None

    def test_get_price_different_products(
        self, backend, product, croissant, bolo, channel
    ):
        """Should return correct price for each product."""
        assert backend.get_price("PAO-FRANCES", channel) == 80
        assert backend.get_price("CROISSANT", channel) == 800
        assert backend.get_price("BOLO-CENOURA", channel) == 4500


# =============================================================================
# CHANNEL PRICING BACKEND
# =============================================================================


class TestChannelPricingBackend:
    """Tests for ChannelPricingBackend (price list + fallback)."""

    @pytest.fixture
    def backend(self):
        """Create ChannelPricingBackend instance."""
        return ChannelPricingBackend(
            product_resolver=get_product_resolver(),
            listing_resolver=get_listing_resolver(),
        )

    def test_get_price_from_listing(
        self, backend, product, listing, listing_item, ifood_channel
    ):
        """Should return price from listing when available."""
        price = backend.get_price("PAO-FRANCES", ifood_channel)

        assert price == 120  # R$ 1.20 from iFood listing

    def test_get_price_fallback_to_base(self, backend, product, channel):
        """Should fallback to base price when no listing entry."""
        # channel is 'loja', not 'ifood' - no listing entry
        price = backend.get_price("PAO-FRANCES", channel)

        assert price == 80  # Fallback to base price

    def test_get_price_fallback_for_product_not_in_listing(
        self, backend, croissant, listing, ifood_channel
    ):
        """Should fallback when product not in listing."""
        # croissant has no ListingItem for ifood
        price = backend.get_price("CROISSANT", ifood_channel)

        assert price == 800  # Fallback to base price

    def test_get_price_nonexistent_returns_none(self, backend, channel):
        """Nonexistent product should return None."""
        price = backend.get_price("NONEXISTENT-SKU", channel)

        assert price is None

    def test_respects_listing_active_flag(
        self, backend, product, listing, listing_item, ifood_channel
    ):
        """Should not use inactive listing."""
        # Deactivate listing
        listing.is_active = False
        listing.save()

        price = backend.get_price("PAO-FRANCES", ifood_channel)

        # Should fallback to base price
        assert price == 80


# =============================================================================
# CHANNEL PRICING WITHOUT LISTING RESOLVER
# =============================================================================


class TestChannelPricingWithoutListing:
    """Tests for ChannelPricingBackend without listing resolver."""

    @pytest.fixture
    def backend(self):
        """Create ChannelPricingBackend without listing resolver."""
        return ChannelPricingBackend(
            product_resolver=get_product_resolver(),
            listing_resolver=None,
        )

    def test_always_uses_base_price(
        self, backend, product, listing, listing_item, ifood_channel
    ):
        """Without listing resolver, should always use base price."""
        price = backend.get_price("PAO-FRANCES", ifood_channel)

        # Even with price list entry, returns base price
        assert price == 80


# =============================================================================
# OFFERING CATALOG SERVICE INTEGRATION
# =============================================================================


class TestOfferingCatalogIntegration:
    """Tests using Offering's catalog service directly."""

    def test_catalog_price_matches_pricing_backend(
        self, product, listing, listing_item
    ):
        """Offering catalog.price should match pricing backend results."""
        from shopman.offering import CatalogService

        # Using catalog service
        catalog_price = CatalogService.price("PAO-FRANCES", channel="ifood")

        # Using pricing backend
        backend = ChannelPricingBackend(
            product_resolver=get_product_resolver(),
            listing_resolver=get_listing_resolver(),
        )

        # Create mock channel with ref
        class MockChannel:
            ref = "ifood"

        backend_price = backend.get_price("PAO-FRANCES", MockChannel())

        # Both should return iFood price
        assert catalog_price == 120
        assert backend_price == 120

    def test_catalog_validate_for_ordering(self, product, croissant):
        """Offering catalog.validate provides data useful for Ordering."""
        from shopman.offering import CatalogService

        result = CatalogService.validate("PAO-FRANCES")

        # These fields are useful for Ordering validation
        assert result.valid is True
        assert result.sku == "PAO-FRANCES"
        assert result.name == "Pão Francês"


# =============================================================================
# PROTOCOL COMPLIANCE
# =============================================================================


class TestProtocolCompliance:
    """Tests that pricing backends implement PricingBackend protocol."""

    def test_simple_backend_implements_protocol(self, product):
        """SimplePricingBackend should implement PricingBackend."""
        backend = SimplePricingBackend(product_resolver=get_product_resolver())

        assert isinstance(backend, PricingBackend)

    def test_channel_backend_implements_protocol(self, product):
        """ChannelPricingBackend should implement PricingBackend."""
        backend = ChannelPricingBackend(
            product_resolver=get_product_resolver(),
            listing_resolver=get_listing_resolver(),
        )

        assert isinstance(backend, PricingBackend)

    def test_protocol_method_signature(self, product, channel):
        """get_price should accept (sku, channel) and return int or None."""
        backend = SimplePricingBackend(product_resolver=get_product_resolver())

        result = backend.get_price("PAO-FRANCES", channel)

        assert isinstance(result, (int, type(None)))


# =============================================================================
# TIERED PRICING
# =============================================================================


class TestTieredPricing:
    """Tests for quantity-based tiered pricing."""

    def test_tiered_pricing_via_catalog(self, db, product, listing):
        """Tiered pricing should work via catalog service."""
        from shopman.offering import CatalogService
        from shopman.offering.models import ListingItem

        # Create tiered pricing
        ListingItem.objects.create(
            listing=listing,
            product=product,
            price_q=80,  # R$ 0.80 for qty 1-9
            min_qty=Decimal("1"),
        )
        ListingItem.objects.create(
            listing=listing,
            product=product,
            price_q=70,  # R$ 0.70 for qty 10+
            min_qty=Decimal("10"),
        )

        # Qty 5 should get 80
        price5 = CatalogService.price("PAO-FRANCES", qty=Decimal("5"), channel="ifood")
        assert price5 == 400  # 5 x 80

        # Qty 10 should get 70
        price10 = CatalogService.price("PAO-FRANCES", qty=Decimal("10"), channel="ifood")
        assert price10 == 700  # 10 x 70


# =============================================================================
# PRICE HISTORY
# =============================================================================


class TestPriceHistory:
    """Tests for price history tracking (simple-history integration)."""

    def test_listing_item_has_history(self, product, listing, listing_item):
        """ListingItem should track history via simple-history."""
        # Update price
        listing_item.price_q = 150
        listing_item.save()

        # Check history
        assert listing_item.history.count() == 2  # Create + Update

        # First record should have original price
        first = listing_item.history.order_by("history_date").first()
        assert first.price_q == 120

        # Latest should have new price
        latest = listing_item.history.latest("history_date")
        assert latest.price_q == 150

    def test_product_has_history(self, product):
        """Product should track history via simple-history."""
        original_price = product.base_price_q

        # Update price
        product.base_price_q = 100
        product.save()

        # Check history
        assert product.history.count() == 2

        first = product.history.order_by("history_date").first()
        assert first.base_price_q == original_price

        latest = product.history.latest("history_date")
        assert latest.base_price_q == 100
