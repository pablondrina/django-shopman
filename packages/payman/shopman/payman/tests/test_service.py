"""Tests for PaymentService — full lifecycle coverage."""
from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from shopman.payman.exceptions import PaymentError
from shopman.payman.models import PaymentIntent, PaymentTransaction
from shopman.payman.service import PaymentService


class CreateIntentTests(TestCase):
    def test_create_intent(self) -> None:
        intent = PaymentService.create_intent("ORD-001", 5000, "pix")
        self.assertEqual(intent.order_ref, "ORD-001")
        self.assertEqual(intent.amount_q, 5000)
        self.assertEqual(intent.method, "pix")
        self.assertEqual(intent.status, PaymentIntent.Status.PENDING)
        self.assertTrue(intent.ref.startswith("PAY-"))

    def test_create_intent_with_custom_ref(self) -> None:
        intent = PaymentService.create_intent("ORD-002", 1000, "card", ref="MY-REF-001")
        self.assertEqual(intent.ref, "MY-REF-001")

    def test_create_intent_with_gateway_data(self) -> None:
        intent = PaymentService.create_intent(
            "ORD-003", 2000, "pix",
            gateway="efi", gateway_id="txid_123",
            gateway_data={"qr_code": "00020126..."},
        )
        self.assertEqual(intent.gateway, "efi")
        self.assertEqual(intent.gateway_id, "txid_123")
        self.assertEqual(intent.gateway_data["qr_code"], "00020126...")

    def test_create_intent_with_expiration(self) -> None:
        expires = timezone.now() + timedelta(minutes=30)
        intent = PaymentService.create_intent(
            "ORD-004", 3000, "pix", expires_at=expires,
        )
        self.assertIsNotNone(intent.expires_at)

    def test_create_intent_invalid_amount(self) -> None:
        with self.assertRaises(PaymentError) as ctx:
            PaymentService.create_intent("ORD-ERR", 0, "pix")
        self.assertEqual(ctx.exception.code, "invalid_amount")

    def test_create_intent_negative_amount(self) -> None:
        with self.assertRaises(PaymentError) as ctx:
            PaymentService.create_intent("ORD-ERR", -100, "pix")
        self.assertEqual(ctx.exception.code, "invalid_amount")


class AuthorizeTests(TestCase):
    def test_authorize(self) -> None:
        intent = PaymentService.create_intent("ORD-A", 5000, "pix")
        result = PaymentService.authorize(intent.ref, gateway_id="gw_123")
        self.assertEqual(result.status, PaymentIntent.Status.AUTHORIZED)
        self.assertEqual(result.gateway_id, "gw_123")
        self.assertIsNotNone(result.authorized_at)

    def test_authorize_with_gateway_data(self) -> None:
        intent = PaymentService.create_intent("ORD-A2", 5000, "card")
        result = PaymentService.authorize(
            intent.ref,
            gateway_data={"stripe_pm": "pm_123"},
        )
        self.assertEqual(result.gateway_data["stripe_pm"], "pm_123")

    def test_authorize_expired(self) -> None:
        expires = timezone.now() - timedelta(minutes=1)
        intent = PaymentService.create_intent(
            "ORD-EXP", 5000, "pix", expires_at=expires,
        )
        with self.assertRaises(PaymentError) as ctx:
            PaymentService.authorize(intent.ref)
        self.assertEqual(ctx.exception.code, "intent_expired")

    def test_authorize_already_authorized(self) -> None:
        intent = PaymentService.create_intent("ORD-AA", 5000, "pix")
        PaymentService.authorize(intent.ref)
        with self.assertRaises(PaymentError) as ctx:
            PaymentService.authorize(intent.ref)
        self.assertEqual(ctx.exception.code, "invalid_transition")

    def test_authorize_not_found(self) -> None:
        with self.assertRaises(PaymentError) as ctx:
            PaymentService.authorize("NONEXISTENT")
        self.assertEqual(ctx.exception.code, "intent_not_found")


class CaptureTests(TestCase):
    def test_capture_full(self) -> None:
        intent = PaymentService.create_intent("ORD-C", 5000, "pix")
        PaymentService.authorize(intent.ref)
        txn = PaymentService.capture(intent.ref)
        self.assertEqual(txn.type, PaymentTransaction.Type.CAPTURE)
        self.assertEqual(txn.amount_q, 5000)

        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentIntent.Status.CAPTURED)
        self.assertIsNotNone(intent.captured_at)

    def test_capture_partial(self) -> None:
        intent = PaymentService.create_intent("ORD-CP", 10000, "card")
        PaymentService.authorize(intent.ref)
        txn = PaymentService.capture(intent.ref, amount_q=7000)
        self.assertEqual(txn.amount_q, 7000)

    def test_capture_exceeds_authorized(self) -> None:
        intent = PaymentService.create_intent("ORD-CE", 5000, "pix")
        PaymentService.authorize(intent.ref)
        with self.assertRaises(PaymentError) as ctx:
            PaymentService.capture(intent.ref, amount_q=6000)
        self.assertEqual(ctx.exception.code, "capture_exceeds_authorized")

    def test_capture_without_authorize(self) -> None:
        intent = PaymentService.create_intent("ORD-CNA", 5000, "pix")
        with self.assertRaises(PaymentError) as ctx:
            PaymentService.capture(intent.ref)
        self.assertEqual(ctx.exception.code, "invalid_transition")

    def test_capture_already_captured(self) -> None:
        intent = PaymentService.create_intent("ORD-CAC", 5000, "pix")
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        with self.assertRaises(PaymentError) as ctx:
            PaymentService.capture(intent.ref)
        self.assertEqual(ctx.exception.code, "invalid_transition")


class RefundTests(TestCase):
    def _captured_intent(self, amount_q: int = 10000) -> PaymentIntent:
        intent = PaymentService.create_intent(
            f"ORD-R{PaymentIntent.objects.count()}", amount_q, "pix",
        )
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        return PaymentService.get(intent.ref)

    def test_refund_full(self) -> None:
        intent = self._captured_intent(10000)
        txn = PaymentService.refund(intent.ref)
        self.assertEqual(txn.type, PaymentTransaction.Type.REFUND)
        self.assertEqual(txn.amount_q, 10000)

        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentIntent.Status.REFUNDED)

    def test_refund_partial(self) -> None:
        intent = self._captured_intent(10000)
        txn = PaymentService.refund(intent.ref, amount_q=3000)
        self.assertEqual(txn.amount_q, 3000)

        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentIntent.Status.REFUNDED)

    def test_refund_partial_then_remaining(self) -> None:
        intent = self._captured_intent(10000)
        PaymentService.refund(intent.ref, amount_q=4000)
        txn2 = PaymentService.refund(intent.ref, amount_q=6000)
        self.assertEqual(txn2.amount_q, 6000)

    def test_refund_exceeds_available(self) -> None:
        intent = self._captured_intent(10000)
        PaymentService.refund(intent.ref, amount_q=8000)
        with self.assertRaises(PaymentError) as ctx:
            PaymentService.refund(intent.ref, amount_q=5000)
        self.assertEqual(ctx.exception.code, "amount_exceeds_captured")

    def test_refund_already_fully_refunded(self) -> None:
        intent = self._captured_intent(5000)
        PaymentService.refund(intent.ref)
        with self.assertRaises(PaymentError) as ctx:
            PaymentService.refund(intent.ref)
        self.assertEqual(ctx.exception.code, "already_refunded")

    def test_refund_pending_intent(self) -> None:
        intent = PaymentService.create_intent("ORD-RP", 5000, "pix")
        with self.assertRaises(PaymentError) as ctx:
            PaymentService.refund(intent.ref)
        self.assertEqual(ctx.exception.code, "invalid_transition")

    def test_refund_with_reason(self) -> None:
        intent = self._captured_intent(5000)
        txn = PaymentService.refund(intent.ref, reason="item danificado")
        self.assertIsNotNone(txn)


class CancelTests(TestCase):
    def test_cancel_pending(self) -> None:
        intent = PaymentService.create_intent("ORD-CX1", 5000, "pix")
        result = PaymentService.cancel(intent.ref)
        self.assertEqual(result.status, PaymentIntent.Status.CANCELLED)
        self.assertIsNotNone(result.cancelled_at)

    def test_cancel_authorized(self) -> None:
        intent = PaymentService.create_intent("ORD-CX2", 5000, "card")
        PaymentService.authorize(intent.ref)
        result = PaymentService.cancel(intent.ref)
        self.assertEqual(result.status, PaymentIntent.Status.CANCELLED)

    def test_cancel_captured_fails(self) -> None:
        intent = PaymentService.create_intent("ORD-CX3", 5000, "pix")
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        with self.assertRaises(PaymentError) as ctx:
            PaymentService.cancel(intent.ref)
        self.assertEqual(ctx.exception.code, "invalid_transition")


class FailTests(TestCase):
    def test_fail_pending(self) -> None:
        intent = PaymentService.create_intent("ORD-F1", 5000, "pix")
        result = PaymentService.fail(intent.ref, error_code="gateway_timeout", message="Timeout")
        self.assertEqual(result.status, PaymentIntent.Status.FAILED)
        self.assertEqual(result.gateway_data["error_code"], "gateway_timeout")
        self.assertEqual(result.gateway_data["error_message"], "Timeout")

    def test_fail_authorized(self) -> None:
        intent = PaymentService.create_intent("ORD-F2", 5000, "card")
        PaymentService.authorize(intent.ref)
        result = PaymentService.fail(intent.ref, error_code="declined")
        self.assertEqual(result.status, PaymentIntent.Status.FAILED)

    def test_fail_captured_fails(self) -> None:
        intent = PaymentService.create_intent("ORD-F3", 5000, "pix")
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        with self.assertRaises(PaymentError):
            PaymentService.fail(intent.ref)


class QueryTests(TestCase):
    def test_get(self) -> None:
        created = PaymentService.create_intent("ORD-Q1", 5000, "pix")
        found = PaymentService.get(created.ref)
        self.assertEqual(found.pk, created.pk)

    def test_get_not_found(self) -> None:
        with self.assertRaises(PaymentError) as ctx:
            PaymentService.get("NOPE")
        self.assertEqual(ctx.exception.code, "intent_not_found")

    def test_get_by_order(self) -> None:
        PaymentService.create_intent("ORD-Q2", 5000, "pix")
        PaymentService.create_intent("ORD-Q2", 3000, "card")
        PaymentService.create_intent("ORD-OTHER", 1000, "pix")

        qs = PaymentService.get_by_order("ORD-Q2")
        self.assertEqual(qs.count(), 2)

    def test_get_active_intent(self) -> None:
        PaymentService.create_intent("ORD-Q3", 5000, "pix", ref="PAY-OLD")
        PaymentService.cancel("PAY-OLD")

        active = PaymentService.create_intent("ORD-Q3", 5000, "card", ref="PAY-NEW")

        found = PaymentService.get_active_intent("ORD-Q3")
        self.assertIsNotNone(found)
        self.assertEqual(found.ref, "PAY-NEW")

    def test_get_active_intent_none(self) -> None:
        PaymentService.create_intent("ORD-Q4", 5000, "pix", ref="PAY-DEAD")
        PaymentService.cancel("PAY-DEAD")

        found = PaymentService.get_active_intent("ORD-Q4")
        self.assertIsNone(found)


class AggregateTests(TestCase):
    def test_captured_total(self) -> None:
        intent = PaymentService.create_intent("ORD-AG1", 10000, "pix")
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref, amount_q=7000)
        self.assertEqual(PaymentService.captured_total(intent.ref), 7000)

    def test_refunded_total(self) -> None:
        intent = PaymentService.create_intent("ORD-AG2", 10000, "pix")
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        PaymentService.refund(intent.ref, amount_q=3000)
        self.assertEqual(PaymentService.refunded_total(intent.ref), 3000)

    def test_no_transactions_returns_zero(self) -> None:
        intent = PaymentService.create_intent("ORD-AG3", 10000, "pix")
        self.assertEqual(PaymentService.captured_total(intent.ref), 0)
        self.assertEqual(PaymentService.refunded_total(intent.ref), 0)


class FullLifecycleTests(TestCase):
    """End-to-end lifecycle: create → authorize → capture → partial refund → full refund."""

    def test_pix_lifecycle(self) -> None:
        # 1. Create
        intent = PaymentService.create_intent("ORD-LIFE", 10000, "pix", gateway="efi")
        self.assertEqual(intent.status, PaymentIntent.Status.PENDING)

        # 2. Authorize (gateway confirmed funds available)
        intent = PaymentService.authorize(intent.ref, gateway_id="efi_txid_abc")
        self.assertEqual(intent.status, PaymentIntent.Status.AUTHORIZED)
        self.assertEqual(intent.gateway_id, "efi_txid_abc")

        # 3. Capture
        txn = PaymentService.capture(intent.ref)
        self.assertEqual(txn.amount_q, 10000)
        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentIntent.Status.CAPTURED)

        # 4. Partial refund
        txn2 = PaymentService.refund(intent.ref, amount_q=3000, reason="item faltando")
        self.assertEqual(txn2.amount_q, 3000)
        self.assertEqual(PaymentService.refunded_total(intent.ref), 3000)

        # 5. Refund remaining
        txn3 = PaymentService.refund(intent.ref)
        self.assertEqual(txn3.amount_q, 7000)
        self.assertEqual(PaymentService.refunded_total(intent.ref), 10000)

    def test_card_lifecycle(self) -> None:
        # 1. Create
        intent = PaymentService.create_intent("ORD-CARD", 8000, "card", gateway="stripe")

        # 2. Authorize (3D Secure passed)
        intent = PaymentService.authorize(
            intent.ref,
            gateway_id="pi_stripe_123",
            gateway_data={"payment_method": "pm_visa_4242"},
        )

        # 3. Capture
        txn = PaymentService.capture(intent.ref, gateway_id="ch_stripe_456")
        self.assertEqual(txn.amount_q, 8000)

        # 4. Full refund
        PaymentService.refund(intent.ref, gateway_id="re_stripe_789")
        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentIntent.Status.REFUNDED)

    def test_cancel_before_capture(self) -> None:
        intent = PaymentService.create_intent("ORD-CANC", 5000, "pix")
        PaymentService.authorize(intent.ref)
        result = PaymentService.cancel(intent.ref, reason="cliente desistiu")
        self.assertEqual(result.status, PaymentIntent.Status.CANCELLED)

    def test_fail_on_gateway_error(self) -> None:
        intent = PaymentService.create_intent("ORD-FAIL", 5000, "card")
        result = PaymentService.fail(intent.ref, error_code="card_declined", message="Cartão recusado")
        self.assertEqual(result.status, PaymentIntent.Status.FAILED)
        self.assertEqual(result.gateway_data["error_code"], "card_declined")
