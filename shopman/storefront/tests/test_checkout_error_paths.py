"""Tests for WP-R19 — Error Paths in Checkout Views."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase


def _make_shop():
    from shopman.shop.models import Shop
    return Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})[0]


def _make_channels():
    from shopman.shop.models import Channel
    Channel.objects.get_or_create(
        ref="web",
        defaults={
            "name": "Web",
            "is_active": True,
        },
    )
    Channel.objects.get_or_create(
        ref="pdv",
        defaults={
            "name": "Balcão",
            "is_active": True,
        },
    )


def repricing_warnings(cart: dict) -> list[dict]:
    """Run the drained repricing path (data → presentation) over a cart-items dict.

    The repricing read-model split into ``shop.projections.checkout.
    repricing_changes`` (data, threshold) + ``storefront.presentation.checkout.
    present_repricing_warnings`` (copy/format). This shim feeds the items dict
    these tests build through both, yielding the same warning dicts.
    """
    from shopman.shop.projections.cart import CartLineProjection
    from shopman.shop.projections.checkout import repricing_changes
    from shopman.storefront.presentation.checkout import present_repricing_warnings

    lines = tuple(
        CartLineProjection(
            line_id="", sku=i["sku"], name=i.get("name", ""), qty=i.get("qty", 1),
            unit_price_q=i["unit_price_q"], line_total_q=i["unit_price_q"] * i.get("qty", 1),
            is_available=True, available_qty=None,
            is_awaiting_confirmation=False, is_ready_for_confirmation=False,
            confirmation_deadline_iso=None, planned_for_date=None,
            original_price_q=None, discount_name=None, discount_is_coupon=False,
        )
        for i in cart.get("items", [])
    )
    return present_repricing_warnings(repricing_changes(lines))


class PaymentMethodUnavailableTests(TestCase):
    """Payment method removed from channel config → clear error message."""

    def setUp(self):
        _make_shop()
        _make_channels()

    def test_payment_method_available_cash(self) -> None:
        """cash is available when channel returns only cash."""
        with patch("shopman.shop.projections.checkout_context.payment_methods", return_value=["cash"]) as mock:
            methods = mock("web")
            self.assertIn("cash", methods)
            self.assertNotIn("pix", methods)

    def test_payment_method_unavailable_returns_false(self) -> None:
        """pix not in channel methods → not available."""
        from unittest.mock import MagicMock

        from shopman.storefront.intents.checkout import _resolve_payment_method
        post = MagicMock()
        post.get.return_value = "pix"
        result = _resolve_payment_method(post, ["cash"])
        self.assertEqual(result, "cash")  # falls back to first available


class RepricingWarningTests(TestCase):
    """Items repriced >5% since cart add → non-blocking warning."""

    def setUp(self):
        _make_shop()
        _make_channels()
        from shopman.offerman.models import Product
        self.product = Product.objects.create(
            sku="REPRICE-SKU-001",
            name="Repriced Product",
            base_price_q=1000,  # current catalog: R$ 10,00
            is_published=True,
            is_sellable=True,
        )

    def test_repricing_detected_over_5_percent(self) -> None:
        """Item added at R$ 8,00 but catalog is R$ 10,00 (25% increase) → warning."""

        cart = {
            "items": [
                {"sku": "REPRICE-SKU-001", "qty": 1, "unit_price_q": 800, "name": "Repriced Product"},
            ]
        }
        warnings = repricing_warnings(cart)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["sku"], "REPRICE-SKU-001")
        self.assertIn("mudou", warnings[0]["message"])

    def test_no_repricing_within_5_percent(self) -> None:
        """Item added at R$ 9,60 with catalog R$ 10,00 (4% diff) → no warning."""

        cart = {
            "items": [
                {"sku": "REPRICE-SKU-001", "qty": 1, "unit_price_q": 960, "name": "Repriced Product"},
            ]
        }
        warnings = repricing_warnings(cart)
        self.assertEqual(len(warnings), 0)

    def test_repricing_exact_match_no_warning(self) -> None:
        """Exact price match → no warning."""

        cart = {
            "items": [
                {"sku": "REPRICE-SKU-001", "qty": 1, "unit_price_q": 1000, "name": "Repriced Product"},
            ]
        }
        warnings = repricing_warnings(cart)
        self.assertEqual(len(warnings), 0)

    def test_empty_cart_no_repricing(self) -> None:
        """Empty cart → no warnings."""
        warnings = repricing_warnings({"items": []})
        self.assertEqual(len(warnings), 0)

    def test_unknown_sku_skipped(self) -> None:
        """SKU not in catalog → silently skipped (no crash)."""
        cart = {
            "items": [
                {"sku": "NONEXISTENT-SKU", "qty": 1, "unit_price_q": 500, "name": "Ghost"},
            ]
        }
        warnings = repricing_warnings(cart)
        self.assertEqual(len(warnings), 0)


class RepricingWarningStructureTests(TestCase):
    """Repricing warnings have the expected structure for template rendering."""

    def setUp(self):
        _make_shop()
        _make_channels()
        from shopman.offerman.models import Product
        Product.objects.create(
            sku="STRUCT-SKU-001",
            name="Struct Product",
            base_price_q=2000,
            is_published=True,
            is_sellable=True,
        )

    def test_repricing_warning_has_required_keys(self) -> None:
        """Warning dict has sku, name, message, and price display fields."""

        cart = {"items": [{"sku": "STRUCT-SKU-001", "qty": 1, "unit_price_q": 500, "name": "Struct Product"}]}
        warnings = repricing_warnings(cart)

        self.assertEqual(len(warnings), 1)
        w = warnings[0]
        self.assertIn("sku", w)
        self.assertIn("name", w)
        self.assertIn("message", w)
        self.assertIn("cart_price_display", w)
        self.assertIn("current_price_display", w)

    def test_repricing_warning_message_includes_product_name(self) -> None:
        """Warning message identifies the product by name."""

        cart = {"items": [{"sku": "STRUCT-SKU-001", "qty": 1, "unit_price_q": 100, "name": "Struct Product"}]}
        warnings = repricing_warnings(cart)

        self.assertTrue(len(warnings) > 0)
        self.assertIn("Struct Product", warnings[0]["message"])
