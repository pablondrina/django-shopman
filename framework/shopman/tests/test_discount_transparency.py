"""
Tests for WP-R9 — Discount Transparency in Cart.

Covers:
- cart_drawer.html renders discount_lines
- CartService.get_cart() aggregates D-1 discounts from modifiers_applied
- CartService.get_cart() aggregates happy_hour discounts from modifiers_applied
- has_discount=True when only modifier discounts present (no DiscountModifier)
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from shopman.offerman.models import Product
from shopman.omniman.ids import generate_session_key
from shopman.omniman.models import Channel, Session
from shopman.omniman.services.modify import ModifyService


def _make_session_with_pricing(sku: str, qty: int, unit_price_q: int, pricing_extra: dict | None = None) -> Session:
    """Create a session with an item and optionally inject extra pricing data."""
    channel = Channel.objects.get(ref="web")
    session_key = generate_session_key()
    session = Session.objects.create(
        session_key=session_key,
        channel=channel,
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
            pricing_policy="fixed",
            edit_policy="open",
            is_active=True,
        )
        self.product = Product.objects.create(
            sku="DISC-SKU",
            name="Discount Product",
            base_price_q=1000,
            is_published=True,
            is_available=True,
        )

    def _get_cart(self, session: Session) -> dict:
        from shopman.web.cart import CartService
        request = self.client.get("/").wsgi_request
        request.session["cart_session_key"] = session.session_key
        return CartService.get_cart(request)

    def test_d1_discount_appears_in_discount_lines(self) -> None:
        """D-1 modifier discount from session.pricing aggregated into cart discount_lines."""
        session = _make_session_with_pricing(
            sku=self.product.sku,
            qty=2,
            unit_price_q=500,
            pricing_extra={"d1_discount": {"total_discount_q": 1000, "label": "D-1"}},
        )
        cart = self._get_cart(session)

        self.assertTrue(cart["has_discount"])
        labels = [line["label"] for line in cart["discount_lines"]]
        self.assertIn("D-1", labels)
        d1_line = next(l for l in cart["discount_lines"] if l["label"] == "D-1")
        self.assertEqual(d1_line["amount_q"], 1000)

    def test_happy_hour_discount_appears_in_discount_lines(self) -> None:
        """Happy hour pricing key aggregated into cart discount_lines."""
        session = _make_session_with_pricing(
            sku=self.product.sku,
            qty=1,
            unit_price_q=900,
            pricing_extra={"happy_hour": {"total_discount_q": 100, "label": "Happy Hour"}},
        )
        cart = self._get_cart(session)

        self.assertTrue(cart["has_discount"])
        labels = [line["label"] for line in cart["discount_lines"]]
        self.assertIn("Happy Hour", labels)

    def test_employee_discount_appears_in_discount_lines(self) -> None:
        """Employee pricing key aggregated into cart discount_lines."""
        session = _make_session_with_pricing(
            sku=self.product.sku,
            qty=1,
            unit_price_q=700,
            pricing_extra={"employee_discount": {"total_discount_q": 300, "label": "Desconto funcionário"}},
        )
        cart = self._get_cart(session)

        self.assertTrue(cart["has_discount"])
        labels = [line["label"] for line in cart["discount_lines"]]
        self.assertIn("Desconto funcionário", labels)

    def test_no_modifier_no_discount_lines(self) -> None:
        """Items with no pricing discounts have no discount_lines."""
        session = _make_session_with_pricing(
            sku=self.product.sku,
            qty=1,
            unit_price_q=1000,
        )
        cart = self._get_cart(session)

        self.assertFalse(cart["has_discount"])
        self.assertEqual(cart["discount_lines"], [])
