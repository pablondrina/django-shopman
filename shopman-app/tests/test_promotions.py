"""
Tests for WP-S6 — Pricing Avançado.

Covers:
- D1DiscountModifier
- PromotionModifier
- CouponModifier
- Promotion / Coupon models
- Coupon cart endpoint
- Qty-aware pricing
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import Mock

from django.test import TestCase
from django.utils import timezone

from shop.models import Coupon, Promotion
from shop.modifiers import CouponModifier, D1DiscountModifier, PromotionModifier

# ── Helpers ──


def _mock_session(items, data=None, pricing=None):
    session = Mock()
    session.items = items
    session.data = data or {}
    session.pricing = pricing
    session.update_items = Mock()
    return session


def _mock_channel(config=None):
    channel = Mock()
    channel.config = config or {}
    channel.ref = "test"
    return channel


# ── D1DiscountModifier ──


class D1DiscountModifierTests(TestCase):

    def test_applies_50pct_default_when_d1(self):
        items = [{"sku": "BREAD", "qty": 1, "unit_price_q": 1000, "is_d1": True}]
        session = _mock_session(items)
        channel = _mock_channel()

        D1DiscountModifier().apply(channel=channel, session=session, ctx={})

        self.assertEqual(items[0]["unit_price_q"], 500)
        self.assertEqual(items[0]["line_total_q"], 500)
        applied = items[0]["modifiers_applied"]
        self.assertEqual(len(applied), 1)
        self.assertEqual(applied[0]["type"], "d1_discount")
        self.assertEqual(applied[0]["discount_percent"], 50)
        self.assertEqual(applied[0]["original_price_q"], 1000)

    def test_skips_non_d1_items(self):
        items = [{"sku": "BREAD", "qty": 1, "unit_price_q": 1000}]
        session = _mock_session(items)
        channel = _mock_channel()

        D1DiscountModifier().apply(channel=channel, session=session, ctx={})

        self.assertEqual(items[0]["unit_price_q"], 1000)
        self.assertNotIn("modifiers_applied", items[0])

    def test_configurable_percent_via_channel(self):
        items = [{"sku": "BREAD", "qty": 1, "unit_price_q": 1000, "is_d1": True}]
        session = _mock_session(items)
        channel = _mock_channel(config={"rules": {"d1_discount_percent": 30}})

        D1DiscountModifier().apply(channel=channel, session=session, ctx={})

        self.assertEqual(items[0]["unit_price_q"], 700)

    def test_reads_d1_from_availability_data(self):
        items = [{"sku": "BREAD", "qty": 1, "unit_price_q": 1000}]
        data = {"availability": {"BREAD": {"is_d1": True}}}
        session = _mock_session(items, data=data)
        channel = _mock_channel()

        D1DiscountModifier().apply(channel=channel, session=session, ctx={})

        self.assertEqual(items[0]["unit_price_q"], 500)

    def test_constructor_override(self):
        items = [{"sku": "BREAD", "qty": 1, "unit_price_q": 1000, "is_d1": True}]
        session = _mock_session(items)
        channel = _mock_channel()

        D1DiscountModifier(discount_percent=25).apply(channel=channel, session=session, ctx={})

        self.assertEqual(items[0]["unit_price_q"], 750)

    def test_code_and_order(self):
        m = D1DiscountModifier()
        self.assertEqual(m.code, "shop.d1_discount")
        self.assertEqual(m.order, 15)


# ── PromotionModifier ──


class PromotionModifierTests(TestCase):

    def setUp(self):
        now = timezone.now()
        self.promo_pct = Promotion.objects.create(
            name="Summer 10%",
            type=Promotion.PERCENT,
            value=10,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=1),
            is_active=True,
        )
        self.promo_fixed = Promotion.objects.create(
            name="R$2 off bread",
            type=Promotion.FIXED,
            value=200,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=1),
            skus=["BREAD"],
            is_active=True,
        )

    def test_applies_percent_discount(self):
        items = [{"sku": "COFFEE", "qty": 1, "unit_price_q": 1000}]
        session = _mock_session(items)
        channel = _mock_channel()

        PromotionModifier().apply(channel=channel, session=session, ctx={})

        self.assertEqual(items[0]["unit_price_q"], 900)
        applied = items[0]["modifiers_applied"]
        self.assertEqual(applied[0]["type"], "promotion")
        self.assertEqual(applied[0]["promotion_name"], "Summer 10%")

    def test_applies_fixed_discount_to_matching_sku(self):
        items = [{"sku": "BREAD", "qty": 2, "unit_price_q": 500}]
        session = _mock_session(items)
        channel = _mock_channel()

        PromotionModifier().apply(channel=channel, session=session, ctx={})

        # Fixed R$2 off is better than 10% (50 centavos) for a R$5 item
        self.assertEqual(items[0]["unit_price_q"], 300)
        self.assertEqual(items[0]["line_total_q"], 600)

    def test_sku_filter_excludes_non_matching(self):
        items = [{"sku": "CAKE", "qty": 1, "unit_price_q": 2000}]
        session = _mock_session(items)
        channel = _mock_channel()

        # Only promo_pct applies to CAKE (no SKU restriction)
        # promo_fixed only targets BREAD
        PromotionModifier().apply(channel=channel, session=session, ctx={})

        self.assertEqual(items[0]["unit_price_q"], 1800)

    def test_skips_expired_promotions(self):
        self.promo_pct.valid_until = timezone.now() - timedelta(hours=1)
        self.promo_pct.save()
        self.promo_fixed.valid_until = timezone.now() - timedelta(hours=1)
        self.promo_fixed.save()

        items = [{"sku": "COFFEE", "qty": 1, "unit_price_q": 1000}]
        session = _mock_session(items)
        channel = _mock_channel()

        PromotionModifier().apply(channel=channel, session=session, ctx={})

        self.assertEqual(items[0]["unit_price_q"], 1000)

    def test_skips_inactive_promotions(self):
        self.promo_pct.is_active = False
        self.promo_pct.save()
        self.promo_fixed.is_active = False
        self.promo_fixed.save()

        items = [{"sku": "BREAD", "qty": 1, "unit_price_q": 500}]
        session = _mock_session(items)
        channel = _mock_channel()

        PromotionModifier().apply(channel=channel, session=session, ctx={})

        self.assertEqual(items[0]["unit_price_q"], 500)

    def test_min_order_q_blocks_promotion(self):
        self.promo_pct.min_order_q = 5000
        self.promo_pct.save()

        items = [{"sku": "COFFEE", "qty": 1, "unit_price_q": 1000, "line_total_q": 1000}]
        session = _mock_session(items)
        channel = _mock_channel()

        PromotionModifier().apply(channel=channel, session=session, ctx={})

        # promo_pct blocked by min_order; promo_fixed doesn't match COFFEE
        self.assertEqual(items[0]["unit_price_q"], 1000)

    def test_skips_d1_items(self):
        items = [
            {"sku": "COFFEE", "qty": 1, "unit_price_q": 1000,
             "modifiers_applied": [{"type": "d1_discount"}]},
        ]
        session = _mock_session(items)
        channel = _mock_channel()

        PromotionModifier().apply(channel=channel, session=session, ctx={})

        self.assertEqual(items[0]["unit_price_q"], 1000)

    def test_collection_filter(self):
        now = timezone.now()
        Promotion.objects.create(
            name="Bakery 15%",
            type=Promotion.PERCENT,
            value=15,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=1),
            collections=["bakery"],
            is_active=True,
        )

        items = [{"sku": "MUFFIN", "qty": 1, "unit_price_q": 800}]
        session = _mock_session(items)
        channel = _mock_channel()
        ctx = {"sku_collections": {"MUFFIN": ["bakery", "sweets"]}}

        PromotionModifier().apply(channel=channel, session=session, ctx=ctx)

        # 15% is better than 10%
        self.assertEqual(items[0]["unit_price_q"], 680)

    def test_code_and_order(self):
        m = PromotionModifier()
        self.assertEqual(m.code, "shop.promotion")
        self.assertEqual(m.order, 20)


# ── CouponModifier ──


class CouponModifierTests(TestCase):

    def setUp(self):
        now = timezone.now()
        self.promo = Promotion.objects.create(
            name="Coupon Promo 20%",
            type=Promotion.PERCENT,
            value=20,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=1),
            is_active=True,
        )
        self.coupon = Coupon.objects.create(
            code="SAVE20",
            promotion=self.promo,
            max_uses=100,
            uses_count=0,
            is_active=True,
        )

    def test_applies_coupon_discount(self):
        items = [{"sku": "COFFEE", "qty": 2, "unit_price_q": 1000}]
        session = _mock_session(items, data={"coupon_code": "SAVE20"})
        channel = _mock_channel()

        CouponModifier().apply(channel=channel, session=session, ctx={})

        self.assertEqual(items[0]["unit_price_q"], 800)
        self.assertEqual(items[0]["line_total_q"], 1600)
        applied = items[0]["modifiers_applied"]
        self.assertEqual(applied[0]["type"], "coupon")
        self.assertEqual(applied[0]["coupon_code"], "SAVE20")

        self.assertEqual(session.pricing["coupon"]["code"], "SAVE20")
        self.assertEqual(session.pricing["coupon"]["discount_q"], 400)  # 200 * 2 qty

    def test_ignores_missing_coupon_code(self):
        items = [{"sku": "COFFEE", "qty": 1, "unit_price_q": 1000}]
        session = _mock_session(items)
        channel = _mock_channel()

        CouponModifier().apply(channel=channel, session=session, ctx={})

        self.assertEqual(items[0]["unit_price_q"], 1000)

    def test_ignores_invalid_coupon(self):
        items = [{"sku": "COFFEE", "qty": 1, "unit_price_q": 1000}]
        session = _mock_session(items, data={"coupon_code": "INVALID"})
        channel = _mock_channel()

        CouponModifier().apply(channel=channel, session=session, ctx={})

        self.assertEqual(items[0]["unit_price_q"], 1000)

    def test_ignores_exhausted_coupon(self):
        self.coupon.uses_count = 100
        self.coupon.save()

        items = [{"sku": "COFFEE", "qty": 1, "unit_price_q": 1000}]
        session = _mock_session(items, data={"coupon_code": "SAVE20"})
        channel = _mock_channel()

        CouponModifier().apply(channel=channel, session=session, ctx={})

        self.assertEqual(items[0]["unit_price_q"], 1000)

    def test_ignores_inactive_coupon(self):
        self.coupon.is_active = False
        self.coupon.save()

        items = [{"sku": "COFFEE", "qty": 1, "unit_price_q": 1000}]
        session = _mock_session(items, data={"coupon_code": "SAVE20"})
        channel = _mock_channel()

        CouponModifier().apply(channel=channel, session=session, ctx={})

        self.assertEqual(items[0]["unit_price_q"], 1000)

    def test_ignores_expired_promotion(self):
        self.promo.valid_until = timezone.now() - timedelta(hours=1)
        self.promo.save()

        items = [{"sku": "COFFEE", "qty": 1, "unit_price_q": 1000}]
        session = _mock_session(items, data={"coupon_code": "SAVE20"})
        channel = _mock_channel()

        CouponModifier().apply(channel=channel, session=session, ctx={})

        self.assertEqual(items[0]["unit_price_q"], 1000)

    def test_unlimited_coupon(self):
        self.coupon.max_uses = 0
        self.coupon.save()

        items = [{"sku": "COFFEE", "qty": 1, "unit_price_q": 1000}]
        session = _mock_session(items, data={"coupon_code": "SAVE20"})
        channel = _mock_channel()

        CouponModifier().apply(channel=channel, session=session, ctx={})

        self.assertEqual(items[0]["unit_price_q"], 800)

    def test_skips_d1_items(self):
        items = [
            {"sku": "COFFEE", "qty": 1, "unit_price_q": 500,
             "modifiers_applied": [{"type": "d1_discount"}]},
        ]
        session = _mock_session(items, data={"coupon_code": "SAVE20"})
        channel = _mock_channel()

        CouponModifier().apply(channel=channel, session=session, ctx={})

        self.assertEqual(items[0]["unit_price_q"], 500)

    def test_code_and_order(self):
        m = CouponModifier()
        self.assertEqual(m.code, "shop.coupon")
        self.assertEqual(m.order, 25)


# ── Model tests ──


class PromotionModelTests(TestCase):

    def test_str(self):
        promo = Promotion(name="Flash Sale")
        self.assertEqual(str(promo), "Flash Sale")

    def test_ordering(self):
        now = timezone.now()
        Promotion.objects.create(
            name="Old", type="percent", value=5,
            valid_from=now - timedelta(days=10), valid_until=now - timedelta(days=5),
        )
        Promotion.objects.create(
            name="New", type="percent", value=10,
            valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1),
        )
        promos = list(Promotion.objects.all())
        self.assertEqual(promos[0].name, "New")


class CouponModelTests(TestCase):

    def test_str(self):
        coupon = Coupon(code="HELLO")
        self.assertEqual(str(coupon), "HELLO")

    def test_is_available_active_with_uses_left(self):
        now = timezone.now()
        promo = Promotion.objects.create(
            name="P", type="percent", value=10,
            valid_from=now, valid_until=now + timedelta(days=1),
        )
        coupon = Coupon.objects.create(
            code="TEST", promotion=promo, max_uses=10, uses_count=5, is_active=True,
        )
        self.assertTrue(coupon.is_available)

    def test_is_available_unlimited(self):
        now = timezone.now()
        promo = Promotion.objects.create(
            name="P", type="percent", value=10,
            valid_from=now, valid_until=now + timedelta(days=1),
        )
        coupon = Coupon.objects.create(
            code="UNLIM", promotion=promo, max_uses=0, uses_count=999, is_active=True,
        )
        self.assertTrue(coupon.is_available)

    def test_not_available_when_exhausted(self):
        now = timezone.now()
        promo = Promotion.objects.create(
            name="P", type="percent", value=10,
            valid_from=now, valid_until=now + timedelta(days=1),
        )
        coupon = Coupon.objects.create(
            code="GONE", promotion=promo, max_uses=5, uses_count=5, is_active=True,
        )
        self.assertFalse(coupon.is_available)

    def test_not_available_when_inactive(self):
        now = timezone.now()
        promo = Promotion.objects.create(
            name="P", type="percent", value=10,
            valid_from=now, valid_until=now + timedelta(days=1),
        )
        coupon = Coupon.objects.create(
            code="OFF", promotion=promo, max_uses=0, is_active=False,
        )
        self.assertFalse(coupon.is_available)


# ── Qty-aware pricing ──


class QtyAwarePricingTests(TestCase):

    def test_catalog_backend_passes_qty(self):
        from channels.backends.pricing import CatalogPricingBackend

        backend = CatalogPricingBackend()
        # Verify the method signature accepts qty
        import inspect
        sig = inspect.signature(backend.get_price)
        self.assertIn("qty", sig.parameters)

    def test_item_modifier_passes_qty_to_backend(self):
        from channels.handlers.pricing import ItemPricingModifier

        backend = Mock()
        backend.get_price = Mock(return_value=500)

        modifier = ItemPricingModifier(backend=backend)
        channel = Mock(ref="test")
        session = Mock()
        session.pricing_policy = "internal"
        session.pricing_trace = []
        session.items = [{"line_id": "L1", "sku": "BREAD", "qty": 5}]

        modifier.apply(channel=channel, session=session, ctx={})

        backend.get_price.assert_called_once_with("BREAD", channel, qty=5)

    def test_protocol_accepts_qty(self):
        import inspect

        from channels.protocols import PricingBackend
        sig = inspect.signature(PricingBackend.get_price)
        self.assertIn("qty", sig.parameters)
