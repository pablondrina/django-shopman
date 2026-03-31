"""
Tests for WP-B3: Pricing Cascade Completa.

Covers:
- Price cascade: customer group → channel listing → base price
- Catalog filtering by channel listing
- Tiered pricing (min_qty)
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import Mock

from django.test import TestCase
from shopman.offering.models import Listing, ListingItem, Product
from shopman.ordering.models import Channel

from channels.backends.pricing import OfferingBackend


class PriceCascadeGroupOverChannelOverBaseTests(TestCase):
    """Test the 3-level pricing cascade: group → channel → base."""

    def setUp(self) -> None:
        self.product = Product.objects.create(
            sku="CAKE", name="Cake", base_price_q=1200, is_published=True,
        )
        # Channel listing: R$10.00
        self.channel_listing = Listing.objects.create(ref="web-listing", name="Web Listing", is_active=True)
        ListingItem.objects.create(
            listing=self.channel_listing, product=self.product,
            price_q=1000, min_qty=Decimal("1"), is_published=True, is_available=True,
        )
        # Group listing: R$8.00 (VIP customers)
        self.group_listing = Listing.objects.create(ref="vip-listing", name="VIP Listing", is_active=True)
        ListingItem.objects.create(
            listing=self.group_listing, product=self.product,
            price_q=800, min_qty=Decimal("1"), is_published=True, is_available=True,
        )

        self.channel = Mock(ref="web", listing_ref="web-listing")
        self.backend = OfferingBackend()

    def test_price_from_customer_group_listing(self) -> None:
        """Customer group listing takes priority over channel listing."""
        customer = Mock()
        customer.group = Mock(listing_ref="vip-listing")
        price = self.backend.get_price("CAKE", self.channel, customer=customer)
        self.assertEqual(price, 800)

    def test_price_from_channel_listing(self) -> None:
        """Channel listing used when no customer group."""
        price = self.backend.get_price("CAKE", self.channel)
        self.assertEqual(price, 1000)

    def test_price_fallback_to_base_price(self) -> None:
        """Base price used when no listing matches."""
        channel_no_listing = Mock(ref="bare", listing_ref=None)
        price = self.backend.get_price("CAKE", channel_no_listing)
        self.assertEqual(price, 1200)

    def test_customer_without_group_uses_channel(self) -> None:
        """Customer without group falls through to channel listing."""
        customer = Mock()
        customer.group = None
        price = self.backend.get_price("CAKE", self.channel, customer=customer)
        self.assertEqual(price, 1000)

    def test_customer_group_without_listing_uses_channel(self) -> None:
        """Customer group without listing_ref falls through to channel listing."""
        customer = Mock()
        customer.group = Mock(listing_ref="")
        price = self.backend.get_price("CAKE", self.channel, customer=customer)
        self.assertEqual(price, 1000)


class TieredPricingMinQtyTests(TestCase):
    """Test that min_qty tiers are respected in the cascade."""

    def setUp(self) -> None:
        self.product = Product.objects.create(
            sku="BREAD", name="Bread", base_price_q=600, is_published=True,
        )
        self.listing = Listing.objects.create(ref="shop", name="Shop", is_active=True)
        # Tiers: 1+ = R$5.00, 5+ = R$4.00, 10+ = R$3.50
        ListingItem.objects.create(
            listing=self.listing, product=self.product,
            price_q=500, min_qty=Decimal("1"), is_published=True, is_available=True,
        )
        ListingItem.objects.create(
            listing=self.listing, product=self.product,
            price_q=400, min_qty=Decimal("5"), is_published=True, is_available=True,
        )
        ListingItem.objects.create(
            listing=self.listing, product=self.product,
            price_q=350, min_qty=Decimal("10"), is_published=True, is_available=True,
        )
        self.channel = Mock(ref="shop", listing_ref="shop")
        self.backend = OfferingBackend()

    def test_qty_1_returns_first_tier(self) -> None:
        price = self.backend.get_price("BREAD", self.channel, qty=1)
        self.assertEqual(price, 500)

    def test_qty_5_returns_second_tier(self) -> None:
        price = self.backend.get_price("BREAD", self.channel, qty=5)
        self.assertEqual(price, 400)

    def test_qty_10_returns_third_tier(self) -> None:
        price = self.backend.get_price("BREAD", self.channel, qty=10)
        self.assertEqual(price, 350)

    def test_qty_7_returns_second_tier(self) -> None:
        """Qty between tiers gets the lower tier price."""
        price = self.backend.get_price("BREAD", self.channel, qty=7)
        self.assertEqual(price, 400)

    def test_qty_100_returns_highest_tier(self) -> None:
        price = self.backend.get_price("BREAD", self.channel, qty=100)
        self.assertEqual(price, 350)


class CatalogFilteredByChannelListingTests(TestCase):
    """Test that catalog views filter products by channel listing."""

    def setUp(self) -> None:
        self.listing = Listing.objects.create(ref="web-listing", name="Web Listing", is_active=True)
        self.channel = Channel.objects.create(
            ref="web", name="Web", listing_ref="web-listing",
            pricing_policy="internal", config={},
        )

        # Product IN the listing
        self.product_in = Product.objects.create(
            sku="IN-LISTING", name="In Listing", base_price_q=500,
            is_published=True, is_available=True,
        )
        ListingItem.objects.create(
            listing=self.listing, product=self.product_in,
            price_q=500, min_qty=Decimal("1"), is_published=True, is_available=True,
        )

        # Product NOT in the listing
        self.product_out = Product.objects.create(
            sku="NOT-IN-LISTING", name="Not In Listing", base_price_q=500,
            is_published=True, is_available=True,
        )

    def test_published_products_filters_by_listing(self) -> None:
        from channels.web.views.catalog import _published_products

        qs = _published_products("web-listing")
        skus = list(qs.values_list("sku", flat=True))
        self.assertIn("IN-LISTING", skus)
        self.assertNotIn("NOT-IN-LISTING", skus)

    def test_published_products_no_listing_shows_all(self) -> None:
        from channels.web.views.catalog import _published_products

        qs = _published_products(None)
        skus = list(qs.values_list("sku", flat=True))
        self.assertIn("IN-LISTING", skus)
        self.assertIn("NOT-IN-LISTING", skus)

    def test_unpublished_listing_item_excluded(self) -> None:
        from channels.web.views.catalog import _published_products

        # Mark listing item as unpublished
        ListingItem.objects.filter(product=self.product_in).update(is_published=False)
        qs = _published_products("web-listing")
        skus = list(qs.values_list("sku", flat=True))
        self.assertNotIn("IN-LISTING", skus)

    def test_unavailable_listing_item_excluded(self) -> None:
        from channels.web.views.catalog import _published_products

        ListingItem.objects.filter(product=self.product_in).update(is_available=False)
        qs = _published_products("web-listing")
        skus = list(qs.values_list("sku", flat=True))
        self.assertNotIn("IN-LISTING", skus)

    def test_inactive_listing_excluded(self) -> None:
        from channels.web.views.catalog import _published_products

        self.listing.is_active = False
        self.listing.save()
        qs = _published_products("web-listing")
        skus = list(qs.values_list("sku", flat=True))
        self.assertNotIn("IN-LISTING", skus)


class PriceHelperChannelAwareTests(TestCase):
    """Test that _get_price_q uses channel listing_ref."""

    def setUp(self) -> None:
        self.listing = Listing.objects.create(ref="storefront", name="Storefront", is_active=True)
        self.product = Product.objects.create(
            sku="COFFEE", name="Coffee", base_price_q=500,
            is_published=True, is_available=True,
        )
        ListingItem.objects.create(
            listing=self.listing, product=self.product,
            price_q=450, min_qty=Decimal("1"), is_published=True, is_available=True,
        )

    def test_get_price_q_with_listing_ref(self) -> None:
        from channels.web.views._helpers import _get_price_q

        price = _get_price_q(self.product, listing_ref="storefront")
        self.assertEqual(price, 450)

    def test_get_price_q_without_listing_ref_fallback(self) -> None:
        from channels.web.views._helpers import _get_price_q

        price = _get_price_q(self.product, listing_ref=None)
        # No channel in DB with ref="web", so falls back to base price
        self.assertEqual(price, 500)

    def test_get_price_q_nonexistent_listing(self) -> None:
        from channels.web.views._helpers import _get_price_q

        price = _get_price_q(self.product, listing_ref="nonexistent")
        self.assertEqual(price, 500)
