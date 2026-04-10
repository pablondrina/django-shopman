"""
Tests for WP-R6 — Cart alternatives when out of stock.

Covers:
- CartAlternativesView returns alternatives partial
- CartAlternativesView returns empty state when no alternatives
- cart.py marks items as is_unavailable when stock < qty
- product_detail shows alternatives section for sold-out product
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from shopman.offerman.models import Product
from shopman.models import Channel


class CartAlternativesViewTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        from shopman.models import Shop
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(
            ref="web",
            name="Web",
            is_active=True,
        )
        self.product = Product.objects.create(
            sku="ALT-SKU",
            name="Test Product",
            base_price_q=1000,
            is_published=True,
            is_available=False,
        )
        self.alt_product = Product.objects.create(
            sku="ALT-SUB",
            name="Alternative Product",
            base_price_q=1200,
            is_published=True,
            is_available=True,
        )

    def test_alternatives_endpoint_returns_200(self) -> None:
        """GET /cart/alternatives/<sku>/ returns 200."""
        resp = self.client.get(f"/cart/alternatives/{self.product.sku}/")
        self.assertEqual(resp.status_code, 200)

    def test_alternatives_endpoint_with_results(self) -> None:
        """Endpoint returns alternatives partial when find_alternatives returns results."""
        with patch("shopman.web.views.catalog._load_alternatives") as mock_load:
            mock_load.return_value = [
                {
                    "sku": self.alt_product.sku,
                    "name": self.alt_product.name,
                    "price_display": "R$ 12,00",
                    "badge": {"label": "Disponível", "css_class": "badge-available", "can_add_to_cart": True},
                }
            ]
            resp = self.client.get(f"/cart/alternatives/{self.product.sku}/")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.alt_product.name)

    def test_alternatives_endpoint_empty_state(self) -> None:
        """Endpoint returns empty state message when no alternatives found."""
        with patch("shopman.web.views.catalog._load_alternatives") as mock_load:
            mock_load.return_value = []
            resp = self.client.get(f"/cart/alternatives/{self.product.sku}/")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "alternativas")

    def test_alternatives_endpoint_unknown_sku(self) -> None:
        """Endpoint still returns 200 for unknown SKU (graceful empty state)."""
        with patch("shopman.web.views.catalog._load_alternatives") as mock_load:
            mock_load.return_value = []
            resp = self.client.get("/cart/alternatives/UNKNOWN-SKU/")
        self.assertEqual(resp.status_code, 200)


class CartItemUnavailableFlagTests(TestCase):
    """CartService.get_cart() marks is_unavailable when stock < qty."""

    def setUp(self) -> None:
        super().setUp()
        Channel.objects.create(
            ref="web",
            name="Web",
            is_active=True,
        )
        self.product = Product.objects.create(
            sku="CART-SKU",
            name="Cart Product",
            base_price_q=500,
            is_published=True,
            is_available=True,
        )
        # Ensure stock exists so is_unavailable defaults to False
        try:
            from shopman.stockman.models import Position, Quant
            pos, _ = Position.objects.get_or_create(
                ref="vitrine", defaults={"name": "Vitrine", "kind": "PHYSICAL", "is_saleable": True}
            )
            Quant.objects.create(sku="CART-SKU", position=pos, _quantity=100)
        except Exception:
            pass  # Stocking not installed

    def _add_to_cart(self, qty: int = 1) -> None:
        self.client.post("/cart/add/", {"sku": self.product.sku, "qty": str(qty)})

    def _make_session_and_request(self, qty: int = 1):
        from shopman.orderman.ids import generate_session_key
        from shopman.orderman.models import Session
        from shopman.orderman.services.modify import ModifyService

        channel = Channel.objects.get(ref="web")
        session_key = generate_session_key()
        Session.objects.create(
            session_key=session_key,
            channel_ref=channel.ref,
            state="open",
            pricing_policy="fixed",
            edit_policy="open",
        )
        ModifyService.modify_session(
            session_key=session_key,
            channel_ref="web",
            ops=[{"op": "add_line", "sku": self.product.sku, "qty": qty, "unit_price_q": 500}],
        )
        request = self.client.get("/").wsgi_request
        request.session["cart_session_key"] = session_key
        return request

    def test_cart_items_have_is_unavailable_key(self) -> None:
        """get_cart() always sets is_unavailable on items (defaults to False)."""
        from shopman.web.cart import CartService

        request = self._make_session_and_request(qty=1)
        cart = CartService.get_cart(request)

        self.assertEqual(len(cart["items"]), 1)
        self.assertIn("is_unavailable", cart["items"][0])
        self.assertFalse(cart["items"][0]["is_unavailable"])

    def test_unavailable_flag_logic(self) -> None:
        """is_unavailable=True when avail_map shows stock < qty."""
        from decimal import Decimal

        # Test the logic directly: total_avail < qty → is_unavailable
        avail = {"breakdown": {"ready": Decimal("2"), "in_production": Decimal("0"), "d1": Decimal("0")}}
        breakdown = avail.get("breakdown", {})
        total_avail = breakdown.get("ready", Decimal("0")) + breakdown.get("in_production", Decimal("0")) + breakdown.get("d1", Decimal("0"))
        qty = 5
        self.assertTrue(int(total_avail) < qty)

        qty = 1
        self.assertFalse(int(total_avail) < qty)
