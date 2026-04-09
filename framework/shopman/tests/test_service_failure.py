"""Tests for WP-R17 — Service Failure Handling (graceful degradation)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase


def _make_order(ref="FAIL-001", total_q=1000):
    from shopman.omniman.models import Channel, Order

    channel, _ = Channel.objects.get_or_create(
        ref="balcao",
        defaults={
            "name": "Balcão",
            "pricing_policy": "fixed",
            "edit_policy": "open",
            "is_active": True,
        },
    )
    return Order.objects.create(
        ref=ref,
        channel=channel,
        status="confirmed",
        total_q=total_q,
        handle_type="phone",
        handle_ref="+5543999001122",
        data={"payment": {"method": "pix"}},
    )


def _make_shop():
    from shopman.models import Shop

    return Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})[0]


class PaymentInitiateFailureTests(TestCase):
    """payment.initiate() fails gracefully when adapter raises."""

    def setUp(self):
        _make_shop()

    def test_adapter_exception_records_error(self) -> None:
        """create_intent() raising records error in payment data.

        Status is NOT written — Payman (PaymentService) is the canonical status source.
        """
        from shopman.services import payment as payment_service

        order = _make_order(ref="FAIL-001")

        mock_adapter = MagicMock()
        mock_adapter.create_intent.side_effect = TimeoutError("Gateway timeout")

        with patch("shopman.services.payment.get_adapter", return_value=mock_adapter):
            payment_service.initiate(order)

        order.refresh_from_db()
        payment = order.data.get("payment", {})
        self.assertNotIn("status", payment)
        self.assertIn("error", payment)
        self.assertIn("Gateway timeout", payment["error"])

    def test_adapter_exception_preserves_method(self) -> None:
        """Pending retry entry still stores the payment method."""
        from shopman.services import payment as payment_service

        order = _make_order(ref="FAIL-002")
        mock_adapter = MagicMock()
        mock_adapter.create_intent.side_effect = ConnectionError("Connection refused")

        with patch("shopman.services.payment.get_adapter", return_value=mock_adapter):
            payment_service.initiate(order)

        order.refresh_from_db()
        payment = order.data.get("payment", {})
        self.assertEqual(payment.get("method"), "pix")
        self.assertEqual(payment.get("amount_q"), 1000)

    def test_adapter_exception_error_truncated_at_200(self) -> None:
        """Long error messages are truncated to 200 chars."""
        from shopman.services import payment as payment_service

        order = _make_order(ref="FAIL-003")
        mock_adapter = MagicMock()
        mock_adapter.create_intent.side_effect = RuntimeError("X" * 500)

        with patch("shopman.services.payment.get_adapter", return_value=mock_adapter):
            payment_service.initiate(order)

        order.refresh_from_db()
        error = order.data.get("payment", {}).get("error", "")
        self.assertLessEqual(len(error), 200)

    def test_no_adapter_is_silent_no_op(self) -> None:
        """No adapter for method → silent no-op, order unchanged."""
        from shopman.services import payment as payment_service

        order = _make_order(ref="FAIL-004")
        with patch("shopman.services.payment.get_adapter", return_value=None):
            payment_service.initiate(order)

        order.refresh_from_db()
        # status not set to pending_retry — adapter was absent, not failed
        self.assertNotEqual(order.data.get("payment", {}).get("status"), "pending_retry")

    def test_successful_initiate_not_affected(self) -> None:
        """Happy path: successful create_intent is not changed."""
        from shopman.adapters.payment_types import PaymentIntent
        from shopman.services import payment as payment_service

        order = _make_order(ref="FAIL-005")
        mock_adapter = MagicMock()
        mock_adapter.create_intent.return_value = PaymentIntent(
            intent_ref="pi_test_123",
            status="pending",
            amount_q=order.total_q,
        )

        with patch("shopman.services.payment.get_adapter", return_value=mock_adapter):
            payment_service.initiate(order)

        order.refresh_from_db()
        payment = order.data.get("payment", {})
        self.assertEqual(payment.get("intent_ref"), "pi_test_123")
        self.assertNotEqual(payment.get("status"), "pending_retry")


class StockCheckDegradationTests(TestCase):
    """_check_cart_stock returns ([], True) when stock service is down."""

    def setUp(self):
        _make_shop()
        from shopman.omniman.models import Channel

        Channel.objects.get_or_create(
            ref="balcao",
            defaults={
                "name": "Balcão",
                "pricing_policy": "fixed",
                "edit_policy": "open",
                "is_active": True,
            },
        )

    def _make_request(self):
        from django.contrib.auth import get_user_model
        from django.test import RequestFactory

        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username="stock_test_user",
            defaults={"is_staff": True},
        )
        request = RequestFactory().get("/checkout/")
        request.user = user
        request.session = {}
        return request

    def _make_cart(self, skus=("SKU-A", "SKU-B")):
        return {
            "items": [
                {"sku": sku, "qty": 1, "name": sku, "line_id": f"L-{sku}"}
                for sku in skus
            ]
        }

    def test_all_unavailable_returns_service_down_flag(self) -> None:
        """When every _get_availability returns None → service_unavailable=True."""
        from shopman.web.views.checkout import CheckoutView

        view = CheckoutView()
        cart = self._make_cart()
        request = self._make_request()

        with patch("shopman.web.views.checkout._get_availability", return_value=None):
            errors, service_unavailable = view._check_cart_stock(request, cart)

        self.assertTrue(service_unavailable)
        self.assertEqual(errors, [])

    def test_partial_unavailable_not_flagged_as_service_down(self) -> None:
        """When only some items fail → service_unavailable=False (partial degradation)."""
        from decimal import Decimal

        from shopman.web.views.checkout import CheckoutView

        view = CheckoutView()
        cart = self._make_cart(skus=("SKU-A", "SKU-B"))
        request = self._make_request()

        avail_ok = {"breakdown": {"ready": Decimal("10"), "in_production": Decimal("0"), "d1": Decimal("0")}}

        def _avail(sku):
            return avail_ok if sku == "SKU-A" else None

        with patch("shopman.web.views.checkout._get_availability", side_effect=_avail):
            errors, service_unavailable = view._check_cart_stock(request, cart)

        self.assertFalse(service_unavailable)

    def test_empty_cart_returns_no_service_down(self) -> None:
        """Empty cart → ([], False)."""
        from shopman.web.views.checkout import CheckoutView

        view = CheckoutView()
        request = self._make_request()
        errors, service_unavailable = view._check_cart_stock(request, {"items": []})
        self.assertFalse(service_unavailable)
        self.assertEqual(errors, [])

    def test_stock_available_no_errors_no_flag(self) -> None:
        """Normal stock → ([], False)."""
        from decimal import Decimal

        from shopman.web.views.checkout import CheckoutView

        view = CheckoutView()
        cart = self._make_cart(skus=("SKU-C",))
        request = self._make_request()
        avail = {"breakdown": {"ready": Decimal("5"), "in_production": Decimal("0"), "d1": Decimal("0")}}

        with patch("shopman.web.views.checkout._get_availability", return_value=avail):
            errors, service_unavailable = view._check_cart_stock(request, cart)

        self.assertFalse(service_unavailable)
        self.assertEqual(errors, [])
