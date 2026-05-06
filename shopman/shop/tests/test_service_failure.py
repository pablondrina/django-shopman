"""Tests for WP-R17 — Service Failure Handling (graceful degradation)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from shopman.orderman.models import Directive


def _make_order(ref="FAIL-001", total_q=1000):
    from shopman.orderman.models import Order

    from shopman.shop.models import Channel

    channel, _ = Channel.objects.get_or_create(
        ref="pdv",
        defaults={
            "name": "Balcão",
            "is_active": True,
        },
    )
    return Order.objects.create(
        ref=ref,
        channel_ref=channel.ref,
        status="confirmed",
        total_q=total_q,
        handle_type="phone",
        handle_ref="+5543999001122",
        data={"payment": {"method": "pix"}},
    )


def _make_shop():
    from shopman.shop.models import Shop

    return Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})[0]


class PaymentInitiateFailureTests(TestCase):
    """payment.initiate() fails gracefully when adapter raises."""

    def setUp(self):
        _make_shop()

    def test_adapter_exception_records_error(self) -> None:
        """create_intent() raising records error in payment data.

        Status is NOT written — Payman (PaymentService) is the canonical status source.
        """
        from shopman.backstage.models import OperatorAlert
        from shopman.shop.services import payment as payment_service

        order = _make_order(ref="FAIL-001")

        mock_adapter = MagicMock()
        mock_adapter.create_intent.side_effect = TimeoutError("Gateway timeout")

        with patch("shopman.shop.services.payment.get_adapter", return_value=mock_adapter):
            payment_service.initiate(order)

        order.refresh_from_db()
        payment = order.data.get("payment", {})
        self.assertNotIn("status", payment)
        self.assertIn("error", payment)
        self.assertIn("Gateway timeout", payment["error"])
        alert = OperatorAlert.objects.get(type="payment_failed", order_ref=order.ref)
        self.assertEqual(alert.severity, "error")
        self.assertIn(order.ref, alert.message)
        directive = Directive.objects.get(topic="notification.send", payload__order_ref=order.ref)
        self.assertEqual(directive.payload["template"], "payment_failed")
        self.assertTrue(directive.payload["requires_active_notification"])

    def test_adapter_exception_preserves_method(self) -> None:
        """Pending retry entry still stores the payment method."""
        from shopman.shop.services import payment as payment_service

        order = _make_order(ref="FAIL-002")
        mock_adapter = MagicMock()
        mock_adapter.create_intent.side_effect = ConnectionError("Connection refused")

        with patch("shopman.shop.services.payment.get_adapter", return_value=mock_adapter):
            payment_service.initiate(order)

        order.refresh_from_db()
        payment = order.data.get("payment", {})
        self.assertEqual(payment.get("method"), "pix")
        self.assertEqual(payment.get("amount_q"), 1000)

    def test_adapter_exception_error_truncated_at_200(self) -> None:
        """Long error messages are truncated to 200 chars."""
        from shopman.shop.services import payment as payment_service

        order = _make_order(ref="FAIL-003")
        mock_adapter = MagicMock()
        mock_adapter.create_intent.side_effect = RuntimeError("X" * 500)

        with patch("shopman.shop.services.payment.get_adapter", return_value=mock_adapter):
            payment_service.initiate(order)

        order.refresh_from_db()
        error = order.data.get("payment", {}).get("error", "")
        self.assertLessEqual(len(error), 200)

    def test_adapter_exception_debounces_operator_alert(self) -> None:
        """Repeated gateway failures should not flood the operator alert surface."""
        from shopman.backstage.models import OperatorAlert
        from shopman.shop.services import payment as payment_service

        order = _make_order(ref="FAIL-004")
        mock_adapter = MagicMock()
        mock_adapter.create_intent.side_effect = TimeoutError("Gateway timeout")

        with patch("shopman.shop.services.payment.get_adapter", return_value=mock_adapter):
            payment_service.initiate(order)
            order.refresh_from_db()
            payment_service.initiate(order)

        self.assertEqual(
            OperatorAlert.objects.filter(type="payment_failed", order_ref=order.ref).count(),
            1,
        )
        self.assertEqual(
            Directive.objects.filter(topic="notification.send", payload__order_ref=order.ref).count(),
            1,
        )

    def test_no_adapter_records_operational_error(self) -> None:
        """No adapter for a digital method is a visible operational error."""
        from shopman.backstage.models import OperatorAlert
        from shopman.shop.services import payment as payment_service

        order = _make_order(ref="FAIL-006")
        with patch("shopman.shop.services.payment.get_adapter", return_value=None):
            payment_service.initiate(order)

        order.refresh_from_db()
        payment = order.data.get("payment", {})
        self.assertNotIn("status", payment)
        self.assertEqual(payment.get("method"), "pix")
        self.assertEqual(payment.get("amount_q"), 1000)
        self.assertIn("error", payment)
        self.assertTrue(
            OperatorAlert.objects.filter(type="payment_failed", order_ref=order.ref).exists()
        )

    @override_settings(
        SHOPMAN_PAYMENT_ADAPTERS={
            "pix": "shopman.shop.adapters.payment_mock",
            "card": "shopman.shop.adapters.payment_mock",
            "cash": None,
            "external": None,
        },
        SHOPMAN_MOCK_PIX_AUTO_CONFIRM=True,
        SHOPMAN_MOCK_PIX_CONFIRM_DELAY_SECONDS=0,
    )
    def test_mock_pix_auto_confirm_setting_schedules_directive(self) -> None:
        """Staging can exercise the paid-order path without gateway credentials."""
        from shopman.shop.services import payment as payment_service

        order = _make_order(ref="FAIL-AUTO-PIX")

        payment_service.initiate(order)

        directive = Directive.objects.get(
            topic="mock_pix.confirm",
            payload__order_ref=order.ref,
        )
        self.assertTrue(directive.payload["mock_pix_auto_confirm"])

    def test_successful_initiate_not_affected(self) -> None:
        """Happy path: successful create_intent is not changed."""
        from shopman.shop.adapters.payment_types import PaymentIntent
        from shopman.shop.services import payment as payment_service

        order = _make_order(ref="FAIL-005")
        mock_adapter = MagicMock()
        mock_adapter.create_intent.return_value = PaymentIntent(
            intent_ref="pi_test_123",
            status="pending",
            amount_q=order.total_q,
        )

        with patch("shopman.shop.services.payment.get_adapter", return_value=mock_adapter):
            payment_service.initiate(order)

        order.refresh_from_db()
        payment = order.data.get("payment", {})
        self.assertEqual(payment.get("intent_ref"), "pi_test_123")
        self.assertTrue(payment.get("idempotency_key", "").startswith(f"order-payment:{order.ref}:pix:"))
        self.assertNotEqual(payment.get("status"), "pending_retry")
        call_kwargs = mock_adapter.create_intent.call_args.kwargs
        self.assertEqual(call_kwargs["metadata"]["idempotency_key"], payment["idempotency_key"])
        self.assertEqual(call_kwargs["idempotency_key"], payment["idempotency_key"])

    def test_successful_initiate_reuses_existing_attempt_idempotency_key(self) -> None:
        """Retries for the same payment attempt keep the same key."""
        from shopman.shop.adapters.payment_types import PaymentIntent
        from shopman.shop.services import payment as payment_service

        order = _make_order(ref="FAIL-010")
        order.data["payment"]["idempotency_key"] = "order-payment:FAIL-010:pix:1000:stable"
        order.save(update_fields=["data", "updated_at"])
        mock_adapter = MagicMock()
        mock_adapter.create_intent.return_value = PaymentIntent(
            intent_ref="pi_stable_123",
            status="pending",
            amount_q=order.total_q,
        )

        with patch("shopman.shop.services.payment.get_adapter", return_value=mock_adapter):
            payment_service.initiate(order)

        order.refresh_from_db()
        payment = order.data.get("payment", {})
        self.assertEqual(payment["idempotency_key"], "order-payment:FAIL-010:pix:1000:stable")
        self.assertEqual(
            mock_adapter.create_intent.call_args.kwargs["idempotency_key"],
            "order-payment:FAIL-010:pix:1000:stable",
        )

    def test_successful_initiate_acknowledges_stale_payment_alert(self) -> None:
        """A recovered payment must not leave an active failed-payment alert."""
        from shopman.backstage.models import OperatorAlert
        from shopman.shop.adapters.payment_types import PaymentIntent
        from shopman.shop.services import payment as payment_service

        order = _make_order(ref="FAIL-007")
        alert = OperatorAlert.objects.create(
            type="payment_failed",
            severity="error",
            order_ref=order.ref,
            message=f"Falha ao gerar pagamento PIX do pedido {order.ref}.",
        )
        mock_adapter = MagicMock()
        mock_adapter.create_intent.return_value = PaymentIntent(
            intent_ref="pi_recovered_123",
            status="pending",
            amount_q=order.total_q,
        )

        with patch("shopman.shop.services.payment.get_adapter", return_value=mock_adapter):
            payment_service.initiate(order)

        alert.refresh_from_db()
        self.assertTrue(alert.acknowledged)

    def test_initiate_reuses_active_payman_intent_when_order_ref_missing(self) -> None:
        """Payman intent is idempotency source when order.data was not persisted."""
        import json

        from django.utils import timezone
        from shopman.orderman.models import Directive
        from shopman.payman import PaymentService

        from shopman.shop.services import payment as payment_service

        order = _make_order(ref="FAIL-008")
        expires_at = timezone.now() + timezone.timedelta(minutes=10)
        intent = PaymentService.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="pix",
            gateway="mock",
            gateway_id="mock-existing",
            gateway_data={
                "client_secret": json.dumps({
                    "qrcode": "PIX-CODE-EXISTING",
                    "brcode": "PIX-CODE-EXISTING",
                    "imagemQrcode": "data:image/png;base64,UElY",
                })
            },
            expires_at=expires_at,
        )
        PaymentService.authorize(intent.ref, gateway_id="mock-existing")
        adapter = MagicMock()
        adapter.create_intent.side_effect = AssertionError("adapter should not be called")

        with patch("shopman.shop.services.payment.get_adapter", return_value=adapter):
            payment_service.initiate(order)
            order.refresh_from_db()
            payment_service.initiate(order)

        order.refresh_from_db()
        payment = order.data["payment"]
        self.assertEqual(payment["intent_ref"], intent.ref)
        self.assertEqual(payment["copy_paste"], "PIX-CODE-EXISTING")
        self.assertEqual(PaymentService.get_by_order(order.ref).count(), 1)
        self.assertEqual(
            Directive.objects.filter(topic="payment.timeout", payload__intent_ref=intent.ref).count(),
            1,
        )

    def test_initiate_recovers_intent_created_before_adapter_exception(self) -> None:
        """A lock after Payman creation should recover instead of creating alert noise."""
        import json

        from django.db import OperationalError
        from django.utils import timezone
        from shopman.payman import PaymentService

        from shopman.backstage.models import OperatorAlert
        from shopman.shop.services import payment as payment_service

        order = _make_order(ref="FAIL-009")
        expires_at = timezone.now() + timezone.timedelta(minutes=10)

        def create_then_fail(**kwargs):
            intent = PaymentService.create_intent(
                order_ref=order.ref,
                amount_q=order.total_q,
                method="pix",
                gateway="mock",
                gateway_id="mock-after-lock",
                gateway_data={
                    "client_secret": json.dumps({
                        "qrcode": "PIX-CODE-RECOVERED",
                        "brcode": "PIX-CODE-RECOVERED",
                        "imagemQrcode": "data:image/png;base64,UElY",
                    })
                },
                expires_at=expires_at,
            )
            PaymentService.authorize(intent.ref, gateway_id="mock-after-lock")
            raise OperationalError("database is locked")

        mock_adapter = MagicMock()
        mock_adapter.create_intent.side_effect = create_then_fail

        with patch("shopman.shop.services.payment.get_adapter", return_value=mock_adapter):
            payment_service.initiate(order)

        order.refresh_from_db()
        self.assertEqual(order.data["payment"]["copy_paste"], "PIX-CODE-RECOVERED")
        self.assertFalse(OperatorAlert.objects.filter(type="payment_failed", order_ref=order.ref).exists())
        self.assertEqual(PaymentService.get_by_order(order.ref).count(), 1)


class StockCheckDegradationTests(TestCase):
    """cart_stock_errors returns ([], True) when stock service is down."""

    def setUp(self):
        _make_shop()
        from shopman.shop.models import Channel

        Channel.objects.get_or_create(
            ref="pdv",
            defaults={
                "name": "Balcão",
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
        from shopman.shop.services.checkout_context import cart_stock_errors

        cart = self._make_cart()
        request = self._make_request()

        with patch("shopman.shop.services.checkout_context._availability_for_sku", return_value=None):
            errors, service_unavailable = cart_stock_errors(
                session_key=request.session.get("cart_session_key", ""),
                cart=cart,
                channel_ref="web",
            )

        self.assertTrue(service_unavailable)
        self.assertEqual(errors, [])

    def test_partial_unavailable_not_flagged_as_service_down(self) -> None:
        """When only some items fail → service_unavailable=False (partial degradation)."""
        from decimal import Decimal

        from shopman.shop.services.checkout_context import cart_stock_errors

        cart = self._make_cart(skus=("SKU-A", "SKU-B"))
        request = self._make_request()

        avail_ok = {"breakdown": {"ready": Decimal("10"), "in_production": Decimal("0"), "d1": Decimal("0")}}

        def _avail(sku, **kwargs):
            return avail_ok if sku == "SKU-A" else None

        with patch("shopman.shop.services.checkout_context._availability_for_sku", side_effect=_avail):
            errors, service_unavailable = cart_stock_errors(
                session_key=request.session.get("cart_session_key", ""),
                cart=cart,
                channel_ref="web",
            )

        self.assertFalse(service_unavailable)

    def test_empty_cart_returns_no_service_down(self) -> None:
        """Empty cart → ([], False)."""
        from shopman.shop.services.checkout_context import cart_stock_errors

        request = self._make_request()
        errors, service_unavailable = cart_stock_errors(
            session_key=request.session.get("cart_session_key", ""),
            cart={"items": []},
            channel_ref="web",
        )
        self.assertFalse(service_unavailable)
        self.assertEqual(errors, [])

    def test_stock_available_no_errors_no_flag(self) -> None:
        """Normal stock → ([], False)."""
        from decimal import Decimal

        from shopman.shop.services.checkout_context import cart_stock_errors

        cart = self._make_cart(skus=("SKU-C",))
        request = self._make_request()
        avail = {"total_promisable": Decimal("5"), "breakdown": {"ready": Decimal("5"), "in_production": Decimal("0"), "d1": Decimal("0")}}

        with patch("shopman.shop.services.checkout_context._availability_for_sku", return_value=avail):
            errors, service_unavailable = cart_stock_errors(
                session_key=request.session.get("cart_session_key", ""),
                cart=cart,
                channel_ref="web",
            )

        self.assertFalse(service_unavailable)
        self.assertEqual(errors, [])
