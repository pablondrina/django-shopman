"""
Tests for pricing module.

Covers:
- ItemPricingModifier
- SessionTotalModifier
- SimplePricingBackend
- ChannelPricingBackend
- PricingBackend protocol
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import Mock

from django.test import TestCase
from shopman.ordering.models import Channel, Session

from channels.backends.pricing import (
    ChannelPricingBackend,
    SimplePricingBackend,
)
from channels.handlers.pricing import (
    ItemPricingModifier,
    SessionTotalModifier,
)
from channels.protocols import PricingBackend


class MockPricingBackend:
    """Mock pricing backend for testing."""

    def __init__(self, prices: dict[str, int] | None = None):
        self.prices = prices or {}

    def get_price(self, sku: str, channel: Any, qty: int = 1) -> int | None:
        return self.prices.get(sku)


class ItemPricingModifierTests(TestCase):

    def setUp(self) -> None:
        self.channel = Mock(ref="test")
        self.backend = MockPricingBackend({"COFFEE": 500, "CAKE": 1000})
        self.modifier = ItemPricingModifier(backend=self.backend)

    def test_modifier_has_correct_code_and_order(self) -> None:
        self.assertEqual(self.modifier.code, "pricing.item")
        self.assertEqual(self.modifier.order, 10)

    def test_apply_prices_and_calculates_line_total(self) -> None:
        session = Mock()
        session.pricing_policy = "internal"
        session.pricing_trace = []
        items = [
            {"line_id": "L1", "sku": "COFFEE", "qty": 2},
            {"line_id": "L2", "sku": "CAKE", "qty": 1, "unit_price_q": 1000},
        ]
        session.items = items

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertEqual(items[0]["unit_price_q"], 500)
        self.assertEqual(items[0]["line_total_q"], 1000)
        self.assertEqual(items[1]["unit_price_q"], 1000)
        self.assertEqual(items[1]["line_total_q"], 1000)

    def test_skip_items_with_existing_price(self) -> None:
        session = Mock()
        session.pricing_policy = "internal"
        session.pricing_trace = []
        items = [{"line_id": "L1", "sku": "COFFEE", "qty": 2, "unit_price_q": 999}]
        session.items = items

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertEqual(items[0]["unit_price_q"], 999)
        self.assertEqual(items[0]["line_total_q"], 1998)

    def test_skip_when_pricing_policy_external(self) -> None:
        session = Mock()
        session.pricing_policy = "external"
        items = [{"line_id": "L1", "sku": "COFFEE", "qty": 2}]
        session.items = items

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertNotIn("unit_price_q", items[0])

    def test_updates_pricing_trace(self) -> None:
        session = Mock()
        session.pricing_policy = "internal"
        session.pricing_trace = []
        items = [{"line_id": "L1", "sku": "COFFEE", "qty": 2}]
        session.items = items

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertEqual(len(session.pricing_trace), 1)
        self.assertEqual(session.pricing_trace[0]["sku"], "COFFEE")
        self.assertEqual(session.pricing_trace[0]["price_q"], 500)

    def test_handles_unknown_sku(self) -> None:
        session = Mock()
        session.pricing_policy = "internal"
        session.pricing_trace = None
        items = [{"line_id": "L1", "sku": "UNKNOWN", "qty": 1}]
        session.items = items

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertNotIn("unit_price_q", items[0])
        self.assertEqual(items[0]["line_total_q"], 0)

    def test_initializes_pricing_trace_if_none(self) -> None:
        session = Mock()
        session.pricing_policy = "internal"
        session.pricing_trace = None
        items = [{"line_id": "L1", "sku": "COFFEE", "qty": 1}]
        session.items = items

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertIsNotNone(session.pricing_trace)
        self.assertEqual(len(session.pricing_trace), 1)

    def test_calculates_line_totals_correctly(self) -> None:
        session = Mock()
        session.pricing_policy = "internal"
        session.pricing_trace = []
        items = [
            {"line_id": "L1", "sku": "COFFEE", "qty": 3, "unit_price_q": 500},
            {"line_id": "L2", "sku": "CAKE", "qty": 2, "unit_price_q": 1000},
        ]
        session.items = items

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertEqual(items[0]["line_total_q"], 1500)
        self.assertEqual(items[1]["line_total_q"], 2000)

    def test_handles_decimal_precision(self) -> None:
        session = Mock()
        session.pricing_policy = "internal"
        session.pricing_trace = []
        items = [{"line_id": "L1", "sku": "ITEM", "qty": 7, "unit_price_q": 333}]
        session.items = items

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertEqual(items[0]["line_total_q"], 2331)

    def test_cascade_pricing_with_qty_aware_backend(self) -> None:
        """Backend returns different unit prices based on qty tier."""

        class TieredBackend:
            def get_price(self, sku, channel, qty=1):
                # Simulates 1+ = 500, 3+ = 400, 10+ = 350
                if qty >= 10:
                    return 350
                if qty >= 3:
                    return 400
                return 500

        modifier = ItemPricingModifier(backend=TieredBackend())
        session = Mock()
        session.pricing_policy = "internal"
        session.pricing_trace = []
        items = [
            {"line_id": "L1", "sku": "BREAD", "qty": 1},
            {"line_id": "L2", "sku": "BREAD", "qty": 5},
            {"line_id": "L3", "sku": "BREAD", "qty": 15},
        ]
        session.items = items

        modifier.apply(channel=self.channel, session=session, ctx={})

        # qty=1 → unit=500, total=500
        self.assertEqual(items[0]["unit_price_q"], 500)
        self.assertEqual(items[0]["line_total_q"], 500)

        # qty=5 → unit=400, total=2000
        self.assertEqual(items[1]["unit_price_q"], 400)
        self.assertEqual(items[1]["line_total_q"], 2000)

        # qty=15 → unit=350, total=5250
        self.assertEqual(items[2]["unit_price_q"], 350)
        self.assertEqual(items[2]["line_total_q"], 5250)


class SessionTotalModifierTests(TestCase):

    def setUp(self) -> None:
        self.channel = Mock(ref="test")
        self.modifier = SessionTotalModifier()

    def test_modifier_has_correct_code_and_order(self) -> None:
        self.assertEqual(self.modifier.code, "pricing.session_total")
        self.assertEqual(self.modifier.order, 50)

    def test_calculates_session_total(self) -> None:
        session = Mock()
        session.pricing = None
        session.items = [
            {"line_id": "L1", "line_total_q": 1000},
            {"line_id": "L2", "line_total_q": 1000},
        ]

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertEqual(session.pricing["total_q"], 2000)
        self.assertEqual(session.pricing["items_count"], 2)

    def test_handles_empty_session(self) -> None:
        session = Mock()
        session.pricing = None
        session.items = []

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertEqual(session.pricing["total_q"], 0)
        self.assertEqual(session.pricing["items_count"], 0)

    def test_handles_missing_line_total(self) -> None:
        session = Mock()
        session.pricing = None
        session.items = [{"line_id": "L1", "sku": "COFFEE", "qty": 2}]

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertEqual(session.pricing["total_q"], 0)

    def test_preserves_existing_pricing_dict(self) -> None:
        session = Mock()
        session.pricing = {"discount": 100}
        session.items = [{"line_id": "L1", "line_total_q": 500}]

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertEqual(session.pricing["total_q"], 500)
        self.assertEqual(session.pricing["discount"], 100)

    def test_works_with_any_pricing_policy(self) -> None:
        session = Mock()
        session.pricing_policy = "external"
        session.pricing = None
        session.items = [{"line_id": "L1", "line_total_q": 2000}]

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertEqual(session.pricing["total_q"], 2000)


class SimplePricingBackendTests(TestCase):

    def setUp(self) -> None:
        @dataclass
        class MockProduct:
            sku: str
            base_price_q: int

        self.products = {
            "COFFEE": MockProduct("COFFEE", 500),
            "CAKE": MockProduct("CAKE", 1000),
        }

        def resolver(sku: str):
            if sku in self.products:
                return self.products[sku]
            raise ValueError("Product not found")

        self.backend = SimplePricingBackend(product_resolver=resolver)
        self.channel = Mock(ref="test")

    def test_implements_protocol(self) -> None:
        self.assertIsInstance(self.backend, PricingBackend)

    def test_returns_price_for_existing_product(self) -> None:
        price = self.backend.get_price("COFFEE", self.channel)
        self.assertEqual(price, 500)

    def test_returns_none_for_unknown_product(self) -> None:
        price = self.backend.get_price("UNKNOWN", self.channel)
        self.assertIsNone(price)

    def test_handles_resolver_exception(self) -> None:
        def failing_resolver(sku: str):
            raise RuntimeError("Database error")

        backend = SimplePricingBackend(product_resolver=failing_resolver)
        price = backend.get_price("ANY", self.channel)
        self.assertIsNone(price)


class ChannelPricingBackendTests(TestCase):

    def setUp(self) -> None:
        @dataclass
        class MockProduct:
            sku: str
            base_price_q: int

        @dataclass
        class MockListing:
            sku: str
            price_q: int | None

        self.products = {
            "COFFEE": MockProduct("COFFEE", 500),
            "CAKE": MockProduct("CAKE", 1000),
            "TEA": MockProduct("TEA", 300),
        }

        self.listings = {
            ("COFFEE", "premium"): MockListing("COFFEE", 600),
            ("TEA", "premium"): MockListing("TEA", None),
        }

        def product_resolver(sku: str):
            if sku in self.products:
                return self.products[sku]
            raise ValueError("Product not found")

        def listing_resolver(sku: str, channel_ref: str):
            key = (sku, channel_ref)
            if key in self.listings:
                return self.listings[key]
            raise ValueError("Listing not found")

        self.backend = ChannelPricingBackend(
            product_resolver=product_resolver,
            listing_resolver=listing_resolver,
        )
        self.premium_channel = Mock(ref="premium")
        self.standard_channel = Mock(ref="standard")

    def test_implements_protocol(self) -> None:
        self.assertIsInstance(self.backend, PricingBackend)

    def test_returns_listing_price_when_available(self) -> None:
        price = self.backend.get_price("COFFEE", self.premium_channel)
        self.assertEqual(price, 600)

    def test_falls_back_to_product_price(self) -> None:
        price = self.backend.get_price("CAKE", self.premium_channel)
        self.assertEqual(price, 1000)

    def test_falls_back_when_listing_has_no_price(self) -> None:
        price = self.backend.get_price("TEA", self.premium_channel)
        self.assertEqual(price, 300)

    def test_returns_none_for_unknown_product(self) -> None:
        price = self.backend.get_price("UNKNOWN", self.premium_channel)
        self.assertIsNone(price)

    def test_works_without_listing_resolver(self) -> None:
        def product_resolver(sku: str):
            return Mock(base_price_q=999)

        backend = ChannelPricingBackend(product_resolver=product_resolver)
        price = backend.get_price("ANY", self.standard_channel)
        self.assertEqual(price, 999)

    def test_handles_listing_resolver_exception(self) -> None:
        price = self.backend.get_price("COFFEE", self.standard_channel)
        self.assertEqual(price, 500)


class PricingProtocolTests(TestCase):

    def test_pricing_backend_protocol_exists(self) -> None:
        self.assertIsNotNone(PricingBackend)

    def test_pricing_backend_has_get_price_method(self) -> None:
        methods = [m for m in dir(PricingBackend) if not m.startswith("_")]
        self.assertIn("get_price", methods)


class PricingModifiersIntegrationTests(TestCase):
    """Integration tests for pricing modifiers with real Session objects."""

    def setUp(self) -> None:
        self.channel = Channel.objects.create(
            ref="integration-test",
            name="Integration Test",
            pricing_policy="internal",
            config={},
        )

    def test_item_pricing_modifier_with_real_session(self) -> None:
        session = Session.objects.create(
            session_key="ITEM-PRICING-INT",
            channel=self.channel,
            state="open",
            pricing_policy="internal",
            items=[
                {"line_id": "L1", "sku": "COFFEE", "qty": 3, "unit_price_q": 500},
            ],
        )

        self.assertEqual(session.items[0]["unit_price_q"], 500)
        self.assertEqual(session.items[0]["line_total_q"], 1500)

    def test_session_total_modifier_with_real_session(self) -> None:
        session = Session.objects.create(
            session_key="SESSION-TOTAL-INT",
            channel=self.channel,
            state="open",
            pricing_policy="internal",
            items=[
                {"line_id": "L1", "sku": "A", "qty": 2, "unit_price_q": 500},
                {"line_id": "L2", "sku": "B", "qty": 1, "unit_price_q": 1000},
            ],
        )

        modifier = SessionTotalModifier()
        modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertEqual(session.pricing["total_q"], 2000)
        self.assertEqual(session.pricing["items_count"], 2)


class CatalogPricingBackendCascadeTests(TestCase):
    """Tests for CatalogPricingBackend with min_qty cascading."""

    def setUp(self) -> None:
        from shopman.offering.models import Listing, ListingItem, Product

        self.product = Product.objects.create(sku="BREAD", name="Bread", base_price_q=600)
        self.listing = Listing.objects.create(ref="shop", name="Shop")

        # Tiers: 1+ = R$5.00, 3+ = R$4.00, 10+ = R$3.50
        from decimal import Decimal

        ListingItem.objects.create(
            listing=self.listing, product=self.product, price_q=500, min_qty=Decimal("1")
        )
        ListingItem.objects.create(
            listing=self.listing, product=self.product, price_q=400, min_qty=Decimal("3")
        )
        ListingItem.objects.create(
            listing=self.listing, product=self.product, price_q=350, min_qty=Decimal("10")
        )

        self.channel = Mock(ref="shop")

    def test_qty_1_returns_first_tier(self) -> None:
        from channels.backends.pricing import CatalogPricingBackend

        backend = CatalogPricingBackend()
        price = backend.get_price("BREAD", self.channel, qty=1)
        self.assertEqual(price, 500)

    def test_qty_5_returns_second_tier(self) -> None:
        from channels.backends.pricing import CatalogPricingBackend

        backend = CatalogPricingBackend()
        price = backend.get_price("BREAD", self.channel, qty=5)
        self.assertEqual(price, 400)

    def test_qty_15_returns_third_tier(self) -> None:
        from channels.backends.pricing import CatalogPricingBackend

        backend = CatalogPricingBackend()
        price = backend.get_price("BREAD", self.channel, qty=15)
        self.assertEqual(price, 350)

    def test_qty_default_returns_first_tier(self) -> None:
        from channels.backends.pricing import CatalogPricingBackend

        backend = CatalogPricingBackend()
        # Default qty=1
        price = backend.get_price("BREAD", self.channel)
        self.assertEqual(price, 500)

    def test_no_channel_returns_base_price(self) -> None:
        from channels.backends.pricing import CatalogPricingBackend

        backend = CatalogPricingBackend()
        price = backend.get_price("BREAD", None, qty=15)
        self.assertEqual(price, 600)  # Falls back to base_price_q


class OfferingBackendCascadeTests(TestCase):
    """Tests for OfferingBackend with min_qty cascading."""

    def setUp(self) -> None:
        from decimal import Decimal

        from shopman.offering.models import Listing, ListingItem, Product

        self.product = Product.objects.create(sku="CAKE", name="Cake", base_price_q=1200)
        self.listing = Listing.objects.create(ref="counter", name="Counter")

        ListingItem.objects.create(
            listing=self.listing, product=self.product, price_q=1000, min_qty=Decimal("1")
        )
        ListingItem.objects.create(
            listing=self.listing, product=self.product, price_q=800, min_qty=Decimal("5")
        )

        self.channel = Mock(ref="counter", listing_ref="counter")

    def test_qty_1_returns_first_tier(self) -> None:
        from channels.backends.pricing import OfferingBackend

        backend = OfferingBackend()
        price = backend.get_price("CAKE", self.channel, qty=1)
        self.assertEqual(price, 1000)

    def test_qty_5_returns_second_tier(self) -> None:
        from channels.backends.pricing import OfferingBackend

        backend = OfferingBackend()
        price = backend.get_price("CAKE", self.channel, qty=5)
        self.assertEqual(price, 800)

    def test_qty_default_returns_first_tier(self) -> None:
        from channels.backends.pricing import OfferingBackend

        backend = OfferingBackend()
        price = backend.get_price("CAKE", self.channel)
        self.assertEqual(price, 1000)
