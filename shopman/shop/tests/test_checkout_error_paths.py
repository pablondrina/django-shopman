"""Tests for WP-R19 — Error Paths in Checkout Views."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
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
        ref="balcao",
        defaults={
            "name": "Balcão",
            "is_active": True,
        },
    )


def _make_staff():
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username="err_staff",
        defaults={"is_staff": True},
    )
    if not user.has_usable_password():
        user.set_password("x")
        user.save()
    return user


class CartExpiredRedirectTests(TestCase):
    """Expired cart session → redirect with flash message."""

    def setUp(self):
        _make_shop()
        _make_channels()
        from shopman.backstage.models import CashRegisterSession
        staff = _make_staff()
        CashRegisterSession.objects.get_or_create(operator=staff, defaults={"opening_amount_q": 0})

    def test_expired_cart_redirects_to_cart_with_message(self) -> None:
        """POST /checkout/ with expired session_key → redirect to /cart/ with message."""
        # Simulate: session_key exists in browser cookie but ordering session is gone
        self.client.get("/")  # warm up session
        session = self.client.session
        session["cart_session_key"] = "EXPIRED-KEY-9999"
        session.save()

        # Patch get_cart to return empty (simulates expired session cleanup)
        with patch("shopman.shop.web.views.checkout.CartService.get_cart") as mock_cart:
            mock_cart.return_value = {
                "items": [],
                "subtotal_q": 0,
                "subtotal_display": "R$ 0,00",
                "count": 0,
                "discount_lines": [],
                "session_key": None,
            }
            # Also simulate that get_cart popped the cart_session_key
            def side_effect(req):
                req.session.pop("cart_session_key", None)
                return mock_cart.return_value
            mock_cart.side_effect = side_effect

            resp = self.client.post("/checkout/", {
                "name": "Test",
                "phone": "5543999001122",
                "fulfillment_type": "pickup",
                "payment_method": "cash",
            })

        self.assertEqual(resp.status_code, 302)
        # Flash message was set
        messages = list(resp.wsgi_request._messages)
        self.assertTrue(any("expirou" in str(m) for m in messages))


class PaymentMethodUnavailableTests(TestCase):
    """Payment method removed from channel config → clear error message."""

    def setUp(self):
        _make_shop()
        _make_channels()

    def test_payment_method_available_counter(self) -> None:
        """counter is always available via _payment_method_available."""
        from shopman.shop.web.views.checkout import CheckoutView
        view = CheckoutView()
        # Patch _get_payment_methods to return only counter
        with patch.object(CheckoutView, "_get_payment_methods", return_value=["cash"]):
            self.assertTrue(view._payment_method_available("cash"))
            self.assertFalse(view._payment_method_available("pix"))

    def test_payment_method_unavailable_returns_false(self) -> None:
        """pix not in channel config → _payment_method_available returns False."""
        from shopman.shop.web.views.checkout import CheckoutView
        view = CheckoutView()
        with patch.object(CheckoutView, "_get_payment_methods", return_value=["cash"]):
            result = view._payment_method_available("pix")
        self.assertFalse(result)


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
        from shopman.shop.web.views.checkout import CheckoutView

        view = CheckoutView()
        cart = {
            "items": [
                {"sku": "REPRICE-SKU-001", "qty": 1, "unit_price_q": 800, "name": "Repriced Product"},
            ]
        }
        warnings = view._check_repricing(cart)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["sku"], "REPRICE-SKU-001")
        self.assertIn("mudou", warnings[0]["message"])

    def test_no_repricing_within_5_percent(self) -> None:
        """Item added at R$ 9,60 with catalog R$ 10,00 (4% diff) → no warning."""
        from shopman.shop.web.views.checkout import CheckoutView

        view = CheckoutView()
        cart = {
            "items": [
                {"sku": "REPRICE-SKU-001", "qty": 1, "unit_price_q": 960, "name": "Repriced Product"},
            ]
        }
        warnings = view._check_repricing(cart)
        self.assertEqual(len(warnings), 0)

    def test_repricing_exact_match_no_warning(self) -> None:
        """Exact price match → no warning."""
        from shopman.shop.web.views.checkout import CheckoutView

        view = CheckoutView()
        cart = {
            "items": [
                {"sku": "REPRICE-SKU-001", "qty": 1, "unit_price_q": 1000, "name": "Repriced Product"},
            ]
        }
        warnings = view._check_repricing(cart)
        self.assertEqual(len(warnings), 0)

    def test_empty_cart_no_repricing(self) -> None:
        """Empty cart → no warnings."""
        from shopman.shop.web.views.checkout import CheckoutView
        view = CheckoutView()
        warnings = view._check_repricing({"items": []})
        self.assertEqual(len(warnings), 0)

    def test_unknown_sku_skipped(self) -> None:
        """SKU not in catalog → silently skipped (no crash)."""
        from shopman.shop.web.views.checkout import CheckoutView
        view = CheckoutView()
        cart = {
            "items": [
                {"sku": "NONEXISTENT-SKU", "qty": 1, "unit_price_q": 500, "name": "Ghost"},
            ]
        }
        warnings = view._check_repricing(cart)
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
        from shopman.shop.web.views.checkout import CheckoutView

        view = CheckoutView()
        cart = {"items": [{"sku": "STRUCT-SKU-001", "qty": 1, "unit_price_q": 500, "name": "Struct Product"}]}
        warnings = view._check_repricing(cart)

        self.assertEqual(len(warnings), 1)
        w = warnings[0]
        self.assertIn("sku", w)
        self.assertIn("name", w)
        self.assertIn("message", w)
        self.assertIn("cart_price_display", w)
        self.assertIn("current_price_display", w)

    def test_repricing_warning_message_includes_product_name(self) -> None:
        """Warning message identifies the product by name."""
        from shopman.shop.web.views.checkout import CheckoutView

        view = CheckoutView()
        cart = {"items": [{"sku": "STRUCT-SKU-001", "qty": 1, "unit_price_q": 100, "name": "Struct Product"}]}
        warnings = view._check_repricing(cart)

        self.assertTrue(len(warnings) > 0)
        self.assertIn("Struct Product", warnings[0]["message"])
