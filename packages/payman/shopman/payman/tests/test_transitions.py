"""Tests for PaymentIntent status transitions and PaymentTransaction immutability."""
from __future__ import annotations

from django.test import TestCase
from shopman.payman.exceptions import PaymentError
from shopman.payman.models import PaymentIntent, PaymentTransaction


class PaymentIntentTransitionTests(TestCase):
    """Verify TRANSITIONS dict is enforced on save()."""

    def _make_intent(self, status=PaymentIntent.Status.PENDING) -> PaymentIntent:
        intent = PaymentIntent.objects.create(
            ref=f"PAY-{PaymentIntent.objects.count():03d}",
            order_ref="ORD-T",
            method="pix",
            amount_q=1000,
        )
        if status != PaymentIntent.Status.PENDING:
            # Walk the transition chain
            chain = {
                PaymentIntent.Status.AUTHORIZED: [PaymentIntent.Status.AUTHORIZED],
                PaymentIntent.Status.CAPTURED: [PaymentIntent.Status.AUTHORIZED, PaymentIntent.Status.CAPTURED],
                PaymentIntent.Status.FAILED: [PaymentIntent.Status.FAILED],
                PaymentIntent.Status.CANCELLED: [PaymentIntent.Status.CANCELLED],
            }
            for step in chain.get(status, []):
                intent.status = step
                intent.save()
        return intent

    # --- Valid transitions ---

    def test_pending_to_authorized(self) -> None:
        intent = self._make_intent()
        intent.status = PaymentIntent.Status.AUTHORIZED
        intent.save()
        self.assertEqual(intent.status, PaymentIntent.Status.AUTHORIZED)

    def test_pending_to_failed(self) -> None:
        intent = self._make_intent()
        intent.status = PaymentIntent.Status.FAILED
        intent.save()
        self.assertEqual(intent.status, PaymentIntent.Status.FAILED)

    def test_pending_to_cancelled(self) -> None:
        intent = self._make_intent()
        intent.status = PaymentIntent.Status.CANCELLED
        intent.save()
        self.assertEqual(intent.status, PaymentIntent.Status.CANCELLED)

    def test_authorized_to_captured(self) -> None:
        intent = self._make_intent(PaymentIntent.Status.AUTHORIZED)
        intent.status = PaymentIntent.Status.CAPTURED
        intent.save()
        self.assertEqual(intent.status, PaymentIntent.Status.CAPTURED)

    def test_authorized_to_cancelled(self) -> None:
        intent = self._make_intent(PaymentIntent.Status.AUTHORIZED)
        intent.status = PaymentIntent.Status.CANCELLED
        intent.save()
        self.assertEqual(intent.status, PaymentIntent.Status.CANCELLED)

    def test_authorized_to_failed(self) -> None:
        intent = self._make_intent(PaymentIntent.Status.AUTHORIZED)
        intent.status = PaymentIntent.Status.FAILED
        intent.save()
        self.assertEqual(intent.status, PaymentIntent.Status.FAILED)

    def test_captured_to_refunded(self) -> None:
        intent = self._make_intent(PaymentIntent.Status.CAPTURED)
        intent.status = PaymentIntent.Status.REFUNDED
        intent.save()
        self.assertEqual(intent.status, PaymentIntent.Status.REFUNDED)

    # --- Invalid transitions ---

    def test_pending_to_captured_invalid(self) -> None:
        intent = self._make_intent()
        intent.status = PaymentIntent.Status.CAPTURED
        with self.assertRaises(PaymentError) as ctx:
            intent.save()
        self.assertEqual(ctx.exception.code, "invalid_transition")

    def test_pending_to_refunded_invalid(self) -> None:
        intent = self._make_intent()
        intent.status = PaymentIntent.Status.REFUNDED
        with self.assertRaises(PaymentError) as ctx:
            intent.save()
        self.assertEqual(ctx.exception.code, "invalid_transition")

    def test_captured_to_authorized_invalid(self) -> None:
        intent = self._make_intent(PaymentIntent.Status.CAPTURED)
        intent.status = PaymentIntent.Status.AUTHORIZED
        with self.assertRaises(PaymentError):
            intent.save()

    def test_failed_is_terminal(self) -> None:
        intent = self._make_intent(PaymentIntent.Status.FAILED)
        intent.status = PaymentIntent.Status.PENDING
        with self.assertRaises(PaymentError):
            intent.save()

    def test_cancelled_is_terminal(self) -> None:
        intent = self._make_intent(PaymentIntent.Status.CANCELLED)
        intent.status = PaymentIntent.Status.AUTHORIZED
        with self.assertRaises(PaymentError):
            intent.save()

    # --- Timestamp auto-set ---

    def test_authorized_at_auto_set(self) -> None:
        intent = self._make_intent()
        self.assertIsNone(intent.authorized_at)
        intent.status = PaymentIntent.Status.AUTHORIZED
        intent.save()
        self.assertIsNotNone(intent.authorized_at)

    def test_captured_at_auto_set(self) -> None:
        intent = self._make_intent(PaymentIntent.Status.AUTHORIZED)
        self.assertIsNone(intent.captured_at)
        intent.status = PaymentIntent.Status.CAPTURED
        intent.save()
        self.assertIsNotNone(intent.captured_at)

    def test_cancelled_at_auto_set(self) -> None:
        intent = self._make_intent()
        self.assertIsNone(intent.cancelled_at)
        intent.status = PaymentIntent.Status.CANCELLED
        intent.save()
        self.assertIsNotNone(intent.cancelled_at)

    def test_timestamp_not_overwritten(self) -> None:
        """If timestamp already set, save() does not overwrite it."""
        from datetime import timedelta

        from django.utils import timezone

        intent = self._make_intent()
        early = timezone.now() - timedelta(hours=1)
        intent.authorized_at = early
        intent.status = PaymentIntent.Status.AUTHORIZED
        intent.save()
        self.assertEqual(intent.authorized_at, early)

    # --- can_transition_to ---

    def test_can_transition_to(self) -> None:
        intent = self._make_intent()
        self.assertTrue(intent.can_transition_to(PaymentIntent.Status.AUTHORIZED))
        self.assertFalse(intent.can_transition_to(PaymentIntent.Status.CAPTURED))


class PaymentTransactionImmutabilityTests(TestCase):
    def setUp(self) -> None:
        self.intent = PaymentIntent.objects.create(
            ref="PAY-IMM", order_ref="ORD-IMM", method="pix", amount_q=10000,
        )
        self.intent.status = PaymentIntent.Status.AUTHORIZED
        self.intent.save()
        self.intent.status = PaymentIntent.Status.CAPTURED
        self.intent.save()

    def test_cannot_update_transaction(self) -> None:
        txn = PaymentTransaction.objects.create(
            intent=self.intent, type="capture", amount_q=10000,
        )
        txn.amount_q = 5000
        with self.assertRaises(ValueError) as ctx:
            txn.save()
        self.assertIn("imutáveis", str(ctx.exception))

    def test_cannot_delete_transaction(self) -> None:
        txn = PaymentTransaction.objects.create(
            intent=self.intent, type="capture", amount_q=10000,
        )
        with self.assertRaises(ValueError) as ctx:
            txn.delete()
        self.assertIn("imutáveis", str(ctx.exception))
