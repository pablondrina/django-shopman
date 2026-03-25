"""
Tests for contrib/payment module.

Covers:
- MockPaymentBackend (now with PaymentService persistence)
- PaymentCaptureHandler
- PaymentRefundHandler
- Payment protocols
"""

from __future__ import annotations

from django.test import TestCase
from shopman.ordering.models import Channel, Directive, Order, Session
from shopman.payments.protocols import (
    CaptureResult,
    GatewayIntent,
    PaymentBackend,
    PaymentStatus,
    RefundResult,
)

from channels.backends.payment_mock import MockPaymentBackend
from channels.handlers.payment import PaymentCaptureHandler, PaymentRefundHandler
from channels.topics import PAYMENT_CAPTURE, PAYMENT_REFUND


class MockPaymentBackendTests(TestCase):
    """Tests for MockPaymentBackend (PaymentService-backed)."""

    def setUp(self) -> None:
        self.backend = MockPaymentBackend()

    def test_create_intent_returns_gateway_intent(self) -> None:
        """Should create intent with authorized status by default."""
        intent = self.backend.create_intent(5000, "BRL", reference="ORD-TEST")

        self.assertIsInstance(intent, GatewayIntent)
        self.assertTrue(intent.intent_id.startswith("PAY-"))
        self.assertEqual(intent.amount_q, 5000)
        self.assertEqual(intent.currency, "BRL")
        self.assertEqual(intent.status, "authorized")
        self.assertIsNotNone(intent.client_secret)

    def test_create_intent_pending_without_auto_authorize(self) -> None:
        """Should create intent with pending status when auto_authorize=False."""
        backend = MockPaymentBackend(auto_authorize=False)
        intent = backend.create_intent(1000, "BRL", reference="ORD-PEND")

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
        intent = backend.create_intent(5000, "BRL", reference="ORD-AUTH")

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
        intent = self.backend.create_intent(5000, "BRL", reference="ORD-CAP")

        result = self.backend.capture(intent.intent_id)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.transaction_id)
        self.assertEqual(result.amount_q, 5000)

    def test_capture_partial_amount(self) -> None:
        """Should capture partial amount."""
        intent = self.backend.create_intent(5000, "BRL", reference="ORD-PART")

        result = self.backend.capture(intent.intent_id, amount_q=3000)

        self.assertTrue(result.success)
        self.assertEqual(result.amount_q, 3000)

    def test_capture_with_reference(self) -> None:
        """Should update reference on capture."""
        intent = self.backend.create_intent(5000, "BRL", reference="ORD-REF")

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
        intent = self.backend.create_intent(5000, "BRL", reference="ORD-DUP")
        self.backend.capture(intent.intent_id)

        result = self.backend.capture(intent.intent_id)

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "invalid_transition")

    def test_refund_success(self) -> None:
        """Should refund captured payment."""
        intent = self.backend.create_intent(5000, "BRL", reference="ORD-RFND")
        self.backend.capture(intent.intent_id)

        result = self.backend.refund(intent.intent_id)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.refund_id)
        self.assertEqual(result.amount_q, 5000)

    def test_refund_partial_amount(self) -> None:
        """Should refund partial amount."""
        intent = self.backend.create_intent(5000, "BRL", reference="ORD-PRFND")
        self.backend.capture(intent.intent_id)

        result = self.backend.refund(intent.intent_id, amount_q=2000)

        self.assertTrue(result.success)
        self.assertEqual(result.amount_q, 2000)

        status = self.backend.get_status(intent.intent_id)
        self.assertEqual(status.refunded_q, 2000)
        # Status is "refunded" because PaymentService transitions on first refund
        self.assertEqual(status.status, "refunded")

    def test_refund_full_changes_status(self) -> None:
        """Should change status to refunded when fully refunded."""
        intent = self.backend.create_intent(5000, "BRL", reference="ORD-FULL")
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
        intent = self.backend.create_intent(5000, "BRL", reference="ORD-NOCAP")

        result = self.backend.refund(intent.intent_id)

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "invalid_transition")

    def test_refund_exceeds_captured(self) -> None:
        """Should return error when refund exceeds captured amount."""
        intent = self.backend.create_intent(5000, "BRL", reference="ORD-EXCEED")
        self.backend.capture(intent.intent_id)

        result = self.backend.refund(intent.intent_id, amount_q=10000)

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "amount_exceeds_captured")

    def test_cancel_success(self) -> None:
        """Should cancel pending/authorized intent."""
        backend = MockPaymentBackend(auto_authorize=False)
        intent = backend.create_intent(5000, "BRL", reference="ORD-CANC")

        result = backend.cancel(intent.intent_id)

        self.assertTrue(result)
        status = backend.get_status(intent.intent_id)
        self.assertEqual(status.status, "cancelled")

    def test_cancel_intent_not_found(self) -> None:
        """Should return False for non-existent intent."""
        result = self.backend.cancel("nonexistent_id")

        self.assertFalse(result)

    def test_cancel_already_captured(self) -> None:
        """Should return False for captured intent."""
        intent = self.backend.create_intent(5000, "BRL", reference="ORD-CAPCL")
        self.backend.capture(intent.intent_id)

        result = self.backend.cancel(intent.intent_id)

        self.assertFalse(result)

    def test_get_status_returns_payment_status(self) -> None:
        """Should return PaymentStatus with correct data."""
        intent = self.backend.create_intent(5000, "BRL", reference="ORD-STAT", metadata={"key": "value"})
        self.backend.capture(intent.intent_id)

        status = self.backend.get_status(intent.intent_id)

        self.assertIsInstance(status, PaymentStatus)
        self.assertEqual(status.intent_id, intent.intent_id)
        self.assertEqual(status.status, "captured")
        self.assertEqual(status.amount_q, 5000)
        self.assertEqual(status.captured_q, 5000)
        self.assertEqual(status.refunded_q, 0)
        self.assertEqual(status.currency, "BRL")

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

    def test_gateway_intent_dataclass(self) -> None:
        """GatewayIntent should be a valid dataclass."""
        intent = GatewayIntent(
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
        self.order = Order.objects.create(
            ref="ORD-PAYMENT-001",
            channel=self.channel,
            status="new",
        )
        self.backend = MockPaymentBackend()
        # Create intent via backend (uses PaymentService)
        self.intent = self.backend.create_intent(
            1000, "BRL", reference=self.order.ref,
        )
        self.session = Session.objects.create(
            session_key="PAYMENT-SESSION",
            channel=self.channel,
            state="committed",
            data={
                "payment": {"intent_id": self.intent.intent_id},
            },
        )
        self.handler = PaymentCaptureHandler(self.backend)

    def test_handler_has_correct_topic(self) -> None:
        """Should have topic='payment.capture'."""
        self.assertEqual(self.handler.topic, PAYMENT_CAPTURE)

    def test_capture_success(self) -> None:
        """Should capture payment and mark directive as done."""
        directive = Directive.objects.create(
            topic=PAYMENT_CAPTURE,
            payload={
                "intent_id": self.intent.intent_id,
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
        self.backend.capture(self.intent.intent_id)

        directive = Directive.objects.create(
            topic=PAYMENT_CAPTURE,
            payload={"intent_id": self.intent.intent_id},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

    def test_capture_no_intent_id_fails(self) -> None:
        """Should fail when no intent_id provided."""
        directive = Directive.objects.create(
            topic=PAYMENT_CAPTURE,
            payload={"order_ref": self.order.ref},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertEqual(directive.last_error, "no_intent_id")

    def test_capture_gets_intent_from_session(self) -> None:
        """Should get intent_id from session if not in payload."""
        directive = Directive.objects.create(
            topic=PAYMENT_CAPTURE,
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
            topic=PAYMENT_CAPTURE,
            payload={
                "intent_id": self.intent.intent_id,
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
        # Create and capture intent via backend
        self.intent = self.backend.create_intent(
            1000, "BRL", reference=self.order.ref,
        )
        self.backend.capture(self.intent.intent_id)
        self.handler = PaymentRefundHandler(self.backend)

    def test_handler_has_correct_topic(self) -> None:
        """Should have topic='payment.refund'."""
        self.assertEqual(self.handler.topic, PAYMENT_REFUND)

    def test_refund_success(self) -> None:
        """Should refund payment and mark directive as done."""
        directive = Directive.objects.create(
            topic=PAYMENT_REFUND,
            payload={
                "intent_id": self.intent.intent_id,
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
            topic=PAYMENT_REFUND,
            payload={
                "intent_id": self.intent.intent_id,
                "amount_q": 500,
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

        status = self.backend.get_status(self.intent.intent_id)
        self.assertEqual(status.refunded_q, 500)

    def test_refund_no_intent_id_fails(self) -> None:
        """Should fail when no intent_id provided."""
        directive = Directive.objects.create(
            topic=PAYMENT_REFUND,
            payload={"order_ref": self.order.ref},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertEqual(directive.last_error, "no_intent_id")

    def test_refund_emits_order_event(self) -> None:
        """Should emit payment.refunded event on order."""
        directive = Directive.objects.create(
            topic=PAYMENT_REFUND,
            payload={
                "intent_id": self.intent.intent_id,
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
        # Create a pending (non-captured) intent
        pending_backend = MockPaymentBackend(auto_authorize=False)
        pending_intent = pending_backend.create_intent(1000, "BRL", reference="ORD-PEND")

        directive = Directive.objects.create(
            topic=PAYMENT_REFUND,
            payload={"intent_id": pending_intent.intent_id},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertIn("invalid_transition", directive.last_error)
