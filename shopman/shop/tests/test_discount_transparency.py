"""
Tests for WP-R9 — Discount Transparency in Cart.

Covers:
- cart_drawer.html renders discount_lines
- shop.projections.cart.build_cart aggregates D-1 discounts from session.pricing
- build_cart aggregates happy_hour discounts from session.pricing
- has_discount=True when only modifier discounts present (no DiscountModifier)
"""

from __future__ import annotations

from django.test import TestCase
from shopman.offerman.models import Product
from shopman.orderman.ids import generate_session_key
from shopman.orderman.models import Session
from shopman.orderman.services.modify import ModifyService

from shopman.shop.models import Channel


def _make_session_with_pricing(sku: str, qty: int, unit_price_q: int, pricing_extra: dict | None = None) -> Session:
    """Create a session with an item and optionally inject extra pricing data."""
    channel = Channel.objects.get(ref="web")
    session_key = generate_session_key()
    session = Session.objects.create(
        session_key=session_key,
        channel_ref=channel.ref,
        state="open",
        pricing_policy="fixed",
        edit_policy="open",
        data={"origin_channel": "web"},
    )
    ModifyService.modify_session(
        session_key=session_key,
        channel_ref="web",
        ops=[{"op": "add_line", "sku": sku, "qty": qty, "unit_price_q": unit_price_q}],
    )
    if pricing_extra:
        session.refresh_from_db()
        pricing = session.pricing or {}
        pricing.update(pricing_extra)
        session.pricing = pricing
        session.save(update_fields=["pricing"])
    session.refresh_from_db()
    return session


class CartDiscountTransparencyTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Channel.objects.create(
            ref="web",
            name="Web",
            is_active=True,
        )
        self.product = Product.objects.create(
            sku="DISC-SKU",
            name="Discount Product",
            base_price_q=1000,
            is_published=True,
            is_sellable=True,
        )

    def _build_cart(self, session: Session):
        """Build the cart DATA projection — the source of discount aggregation."""
        from shopman.shop.projections.cart import build_cart
        return build_cart(session.session_key, "web")

    def test_d1_discount_appears_in_discount_lines(self) -> None:
        """D-1 modifier discount from session.pricing aggregated into cart discount_lines."""
        session = _make_session_with_pricing(
            sku=self.product.sku,
            qty=2,
            unit_price_q=500,
            pricing_extra={"d1_discount": {"total_discount_q": 1000, "label": "D-1"}},
        )
        data = self._build_cart(session)

        self.assertTrue(data.discount_total_q > 0)
        labels = [dl.name for dl in data.discount_lines]
        self.assertIn("D-1", labels)
        d1_line = next(dl for dl in data.discount_lines if dl.name == "D-1")
        self.assertEqual(d1_line.amount_q, 1000)

    def test_happy_hour_discount_appears_in_discount_lines(self) -> None:
        """Happy hour pricing key aggregated into cart discount_lines."""
        session = _make_session_with_pricing(
            sku=self.product.sku,
            qty=1,
            unit_price_q=900,
            pricing_extra={"happy_hour": {"total_discount_q": 100, "label": "Happy Hour"}},
        )
        data = self._build_cart(session)

        self.assertTrue(data.discount_total_q > 0)
        labels = [dl.name for dl in data.discount_lines]
        self.assertIn("Happy Hour", labels)

    def test_employee_discount_appears_in_discount_lines(self) -> None:
        """Employee pricing key aggregated into cart discount_lines."""
        session = _make_session_with_pricing(
            sku=self.product.sku,
            qty=1,
            unit_price_q=700,
            pricing_extra={"employee_discount": {"total_discount_q": 300, "label": "Desconto funcionário"}},
        )
        data = self._build_cart(session)

        self.assertTrue(data.discount_total_q > 0)
        labels = [dl.name for dl in data.discount_lines]
        self.assertIn("Desconto funcionário", labels)

    def test_no_modifier_no_discount_lines(self) -> None:
        """Items with no pricing discounts have no discount_lines."""
        session = _make_session_with_pricing(
            sku=self.product.sku,
            qty=1,
            unit_price_q=1000,
        )
        data = self._build_cart(session)

        self.assertFalse(data.discount_total_q > 0)
        self.assertEqual(data.discount_lines, ())
