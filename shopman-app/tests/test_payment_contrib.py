"""
Tests for contrib/payment module.

Covers:
- MockPaymentBackend
- PaymentCaptureHandler
- PaymentRefundHandler
- Payment protocols
"""

from __future__ import annotations

from django.test import TestCase

from shopman.payment.adapters.mock import MockPaymentBackend
from shopman.payment.handlers import PaymentCaptureHandler, PaymentRefundHandler
from shopman.payment.protocols import (
    CaptureResult,
    PaymentBackend,
    PaymentIntent,
    PaymentStatus,
    RefundResult,
)
from shopman.ordering.models import Channel, Directive, Order, Session


class MockPaymentBackendTests(TestCase):
    """Tests for MockPaymentBackend."""

    def setUp(self) -> None:
        self.backend = MockPaymentBackend()

    def test_create_intent_returns_payment_intent(self) -> None:
        """Should create intent with authorized status by default."""
        intent = self.backend.create_intent(5000, "BRL")

        self.assertIsInstance(intent, PaymentIntent)
        self.assertTrue(intent.intent_id.startswith("mock_pi_"))
        self.assertEqual(intent.amount_q, 5000)
        self.assertEqual(intent.currency, "BRL")
        self.assertEqual(intent.status, "authorized")
        self.assertIsNotNone(intent.client_secret)

    def test_create_intent_pending_without_auto_authorize(self) -> None:
        """Should create intent with pending status when auto_authorize=False."""
        backend = MockPaymentBackend(auto_authorize=False)
        intent = backend.create_intent(1000, "USD")

        self.assertEqual(intent.status, "pending")

    def test_create_intent_with_metadata(self) -> None:
        """Should store metadata in intent."""
        intent = self.backend.create_intent(
            5000, "BRL", reference="ORD-123", metadata={"order_id": "123"}
        )

        self.assertEqual(intent.metadata, {"order_id": "123"})

    def test_authorize_success(self) -> None:
        """Should authorize pending intent."""
        backend = MockPaymentBackend(auto_authorize=False)
        intent = backend.create_intent(5000, "BRL")

        result = backend.authorize(intent.intent_id)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.transaction_id)
        self.assertEqual(result.amount_q, 5000)

    def test_authorize_intent_not_found(self) -> None:
        """Should return error for non-existent intent."""
        result = self.backend.authorize("nonexistent_id")

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "intent_not_found")

    def test_capture_success(self) -> None:
        """Should capture authorized intent."""
        intent = self.backend.create_intent(5000, "BRL")

        result = self.backend.capture(intent.intent_id)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.transaction_id)
        self.assertEqual(result.amount_q, 5000)

    def test_capture_partial_amount(self) -> None:
        """Should capture partial amount."""
        intent = self.backend.create_intent(5000, "BRL")

        result = self.backend.capture(intent.intent_id, amount_q=3000)

        self.assertTrue(result.success)
        self.assertEqual(result.amount_q, 3000)

    def test_capture_with_reference(self) -> None:
        """Should update reference on capture."""
        intent = self.backend.create_intent(5000, "BRL")

        self.backend.capture(intent.intent_id, reference="ORD-456")

        status = self.backend.get_status(intent.intent_id)
        self.assertEqual(status.status, "captured")

    def test_capture_intent_not_found(self) -> None:
        """Should return error for non-existent intent."""
        result = self.backend.capture("nonexistent_id")

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "intent_not_found")

    def test_capture_already_captured(self) -> None:
        """Should return error for already captured intent."""
        intent = self.backend.create_intent(5000, "BRL")
        self.backend.capture(intent.intent_id)

        result = self.backend.capture(intent.intent_id)

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "invalid_status")

    def test_refund_success(self) -> None:
        """Should refund captured payment."""
        intent = self.backend.create_intent(5000, "BRL")
        self.backend.capture(intent.intent_id)

        result = self.backend.refund(intent.intent_id)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.refund_id)
        self.assertEqual(result.amount_q, 5000)

    def test_refund_partial_amount(self) -> None:
        """Should refund partial amount."""
        intent = self.backend.create_intent(5000, "BRL")
        self.backend.capture(intent.intent_id)

        result = self.backend.refund(intent.intent_id, amount_q=2000)

        self.assertTrue(result.success)
        self.assertEqual(result.amount_q, 2000)

        status = self.backend.get_status(intent.intent_id)
        self.assertEqual(status.refunded_q, 2000)
        self.assertEqual(status.status, "captured")  # Still captured, not fully refunded

    def test_refund_full_changes_status(self) -> None:
        """Should change status to refunded when fully refunded."""
        intent = self.backend.create_intent(5000, "BRL")
        self.backend.capture(intent.intent_id)

        self.backend.refund(intent.intent_id)

        status = self.backend.get_status(intent.intent_id)
        self.assertEqual(status.status, "refunded")

    def test_refund_intent_not_found(self) -> None:
        """Should return error for non-existent intent."""
        result = self.backend.refund("nonexistent_id")

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "intent_not_found")

    def test_refund_not_captured(self) -> None:
        """Should return error for non-captured intent."""
        intent = self.backend.create_intent(5000, "BRL")

        result = self.backend.refund(intent.intent_id)

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "not_captured")

    def test_refund_exceeds_captured(self) -> None:
        """Should return error when refund exceeds captured amount."""
        intent = self.backend.create_intent(5000, "BRL")
        self.backend.capture(intent.intent_id)

        result = self.backend.refund(intent.intent_id, amount_q=10000)

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "exceeds_captured")

    def test_cancel_success(self) -> None:
        """Should cancel pending/authorized intent."""
        intent = self.backend.create_intent(5000, "BRL")

        result = self.backend.cancel(intent.intent_id)

        self.assertTrue(result)
        status = self.backend.get_status(intent.intent_id)
        self.assertEqual(status.status, "cancelled")

    def test_cancel_intent_not_found(self) -> None:
        """Should return False for non-existent intent."""
        result = self.backend.cancel("nonexistent_id")

        self.assertFalse(result)

    def test_cancel_already_captured(self) -> None:
        """Should return False for captured intent."""
        intent = self.backend.create_intent(5000, "BRL")
        self.backend.capture(intent.intent_id)

        result = self.backend.cancel(intent.intent_id)

        self.assertFalse(result)

    def test_get_status_returns_payment_status(self) -> None:
        """Should return PaymentStatus with correct data."""
        intent = self.backend.create_intent(5000, "BRL", metadata={"key": "value"})
        self.backend.capture(intent.intent_id)

        status = self.backend.get_status(intent.intent_id)

        self.assertIsInstance(status, PaymentStatus)
        self.assertEqual(status.intent_id, intent.intent_id)
        self.assertEqual(status.status, "captured")
        self.assertEqual(status.amount_q, 5000)
        self.assertEqual(status.captured_q, 5000)
        self.assertEqual(status.refunded_q, 0)
        self.assertEqual(status.currency, "BRL")
        self.assertEqual(status.metadata, {"key": "value"})

    def test_get_status_not_found(self) -> None:
        """Should return not_found status for non-existent intent."""
        status = self.backend.get_status("nonexistent_id")

        self.assertEqual(status.status, "not_found")
        self.assertEqual(status.amount_q, 0)


class PaymentProtocolTests(TestCase):
    """Tests for payment protocols."""

    def test_mock_backend_implements_protocol(self) -> None:
        """MockPaymentBackend should implement PaymentBackend protocol."""
        backend = MockPaymentBackend()
        self.assertIsInstance(backend, PaymentBackend)

    def test_payment_intent_dataclass(self) -> None:
        """PaymentIntent should be a valid dataclass."""
        intent = PaymentIntent(
            intent_id="pi_123",
            status="pending",
            amount_q=1000,
            currency="BRL",
        )

        self.assertEqual(intent.intent_id, "pi_123")
        self.assertIsNone(intent.client_secret)

    def test_capture_result_dataclass(self) -> None:
        """CaptureResult should be a valid dataclass."""
        result = CaptureResult(success=True, transaction_id="txn_123", amount_q=1000)

        self.assertTrue(result.success)
        self.assertEqual(result.transaction_id, "txn_123")

    def test_refund_result_dataclass(self) -> None:
        """RefundResult should be a valid dataclass."""
        result = RefundResult(success=True, refund_id="ref_123", amount_q=500)

        self.assertTrue(result.success)
        self.assertEqual(result.refund_id, "ref_123")


class PaymentCaptureHandlerTests(TestCase):
    """Tests for PaymentCaptureHandler."""

    def setUp(self) -> None:
        self.channel = Channel.objects.create(
            ref="payment-test",
            name="Payment Test",
            pricing_policy="external",
            edit_policy="open",
            config={},
        )
        self.session = Session.objects.create(
            session_key="PAYMENT-SESSION",
            channel=self.channel,
            state="committed",
            data={
                "payment": {"intent_id": "mock_pi_test123"},
            },
        )
        self.order = Order.objects.create(
            ref="ORD-PAYMENT-001",
            channel=self.channel,
            status="new",
        )
        self.backend = MockPaymentBackend()
        # Pre-create intent in backend
        self.backend._intents["mock_pi_test123"] = {
            "intent_id": "mock_pi_test123",
            "status": "authorized",
            "amount_q": 1000,
            "currency": "BRL",
            "captured_q": 0,
            "refunded_q": 0,
            "reference": None,
            "metadata": {},
        }
        self.handler = PaymentCaptureHandler(self.backend)

    def test_handler_has_correct_topic(self) -> None:
        """Should have topic='payment.capture'."""
        self.assertEqual(self.handler.topic, "payment.capture")

    def test_capture_success(self) -> None:
        """Should capture payment and mark directive as done."""
        directive = Directive.objects.create(
            topic="payment.capture",
            payload={
                "intent_id": "mock_pi_test123",
                "order_ref": self.order.ref,
                "amount_q": 1000,
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.assertIn("transaction_id", directive.payload)

    def test_capture_already_captured_is_idempotent(self) -> None:
        """Should mark as done if already captured (idempotent)."""
        # First capture the payment
        self.backend.capture("mock_pi_test123")

        directive = Directive.objects.create(
            topic="payment.capture",
            payload={"intent_id": "mock_pi_test123"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

    def test_capture_no_intent_id_fails(self) -> None:
        """Should fail when no intent_id provided."""
        directive = Directive.objects.create(
            topic="payment.capture",
            payload={"order_ref": self.order.ref},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertEqual(directive.last_error, "no_intent_id")

    def test_capture_gets_intent_from_session(self) -> None:
        """Should get intent_id from session if not in payload."""
        directive = Directive.objects.create(
            topic="payment.capture",
            payload={
                "session_key": self.session.session_key,
                "channel_ref": self.channel.ref,
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

    def test_capture_emits_order_event(self) -> None:
        """Should emit payment.captured event on order."""
        directive = Directive.objects.create(
            topic="payment.capture",
            payload={
                "intent_id": "mock_pi_test123",
                "order_ref": self.order.ref,
            },
        )

        self.handler.handle(message=directive, ctx={})

        self.order.refresh_from_db()
        events = self.order.events.filter(type="payment.captured")
        self.assertEqual(events.count(), 1)


class PaymentRefundHandlerTests(TestCase):
    """Tests for PaymentRefundHandler."""

    def setUp(self) -> None:
        self.channel = Channel.objects.create(
            ref="refund-test",
            name="Refund Test",
            config={},
        )
        self.order = Order.objects.create(
            ref="ORD-REFUND-001",
            channel=self.channel,
            status="completed",
        )
        self.backend = MockPaymentBackend()
        # Pre-create captured intent
        self.backend._intents["mock_pi_refund"] = {
            "intent_id": "mock_pi_refund",
            "status": "captured",
            "amount_q": 1000,
            "currency": "BRL",
            "captured_q": 1000,
            "refunded_q": 0,
            "reference": self.order.ref,
            "metadata": {},
        }
        self.handler = PaymentRefundHandler(self.backend)

    def test_handler_has_correct_topic(self) -> None:
        """Should have topic='payment.refund'."""
        self.assertEqual(self.handler.topic, "payment.refund")

    def test_refund_success(self) -> None:
        """Should refund payment and mark directive as done."""
        directive = Directive.objects.create(
            topic="payment.refund",
            payload={
                "intent_id": "mock_pi_refund",
                "order_ref": self.order.ref,
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.assertIn("refund_id", directive.payload)

    def test_refund_partial_amount(self) -> None:
        """Should refund partial amount."""
        directive = Directive.objects.create(
            topic="payment.refund",
            payload={
                "intent_id": "mock_pi_refund",
                "amount_q": 500,
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

        status = self.backend.get_status("mock_pi_refund")
        self.assertEqual(status.refunded_q, 500)

    def test_refund_no_intent_id_fails(self) -> None:
        """Should fail when no intent_id provided."""
        directive = Directive.objects.create(
            topic="payment.refund",
            payload={"order_ref": self.order.ref},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertEqual(directive.last_error, "no_intent_id")

    def test_refund_emits_order_event(self) -> None:
        """Should emit payment.refunded event on order."""
        directive = Directive.objects.create(
            topic="payment.refund",
            payload={
                "intent_id": "mock_pi_refund",
                "order_ref": self.order.ref,
                "reason": "Customer request",
            },
        )

        self.handler.handle(message=directive, ctx={})

        self.order.refresh_from_db()
        events = self.order.events.filter(type="payment.refunded")
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.first().payload["reason"], "Customer request")

    def test_refund_failure_marks_directive_failed(self) -> None:
        """Should mark directive as failed on refund error."""
        # Use non-captured intent
        self.backend._intents["mock_pi_pending"] = {
            "intent_id": "mock_pi_pending",
            "status": "pending",
            "amount_q": 1000,
            "currency": "BRL",
            "captured_q": 0,
            "refunded_q": 0,
            "reference": None,
            "metadata": {},
        }

        directive = Directive.objects.create(
            topic="payment.refund",
            payload={"intent_id": "mock_pi_pending"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertIn("not_captured", directive.last_error)
