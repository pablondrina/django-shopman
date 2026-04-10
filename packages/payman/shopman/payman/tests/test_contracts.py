"""
Contract tests — document and enforce Payman domain invariants.

These tests serve as executable documentation of the payment domain contracts
described in docs/reference/payment-contracts.md.
"""
from __future__ import annotations

from django.test import TestCase

from shopman.payman.exceptions import PaymentError
from shopman.payman.models import PaymentIntent
from shopman.payman.service import PaymentService


class CaptureContractTests(TestCase):
    """Capture is single-shot: one capture per intent, partial or full."""

    def _authorized_intent(self, amount_q: int = 10000) -> PaymentIntent:
        intent = PaymentService.create_intent("ORD-CAP", amount_q, "pix")
        PaymentService.authorize(intent.ref, gateway_id="gw-1")
        return intent

    def test_full_capture(self) -> None:
        intent = self._authorized_intent(10000)
        txn = PaymentService.capture(intent.ref)
        self.assertEqual(txn.amount_q, 10000)
        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentIntent.Status.CAPTURED)

    def test_partial_capture_abandons_balance(self) -> None:
        """Partial capture: uncaptured balance is abandoned (no second capture)."""
        intent = self._authorized_intent(10000)
        txn = PaymentService.capture(intent.ref, amount_q=7000)
        self.assertEqual(txn.amount_q, 7000)

        # Attempt second capture fails — intent is already CAPTURED
        with self.assertRaises(PaymentError) as ctx:
            PaymentService.capture(intent.ref, amount_q=3000)
        self.assertEqual(ctx.exception.code, "invalid_transition")

    def test_capture_exceeds_authorized_rejected(self) -> None:
        intent = self._authorized_intent(10000)
        with self.assertRaises(PaymentError) as ctx:
            PaymentService.capture(intent.ref, amount_q=15000)
        self.assertEqual(ctx.exception.code, "capture_exceeds_authorized")


class RefundContractTests(TestCase):
    """REFUNDED means 'at least one refund'; refunded_total() is the truth."""

    def _captured_intent(self, amount_q: int = 10000) -> PaymentIntent:
        intent = PaymentService.create_intent("ORD-REF", amount_q, "pix")
        PaymentService.authorize(intent.ref, gateway_id="gw-1")
        PaymentService.capture(intent.ref)
        return intent

    def test_multiple_partial_refunds(self) -> None:
        """Multiple partial refunds allowed while balance remains."""
        intent = self._captured_intent(10000)

        PaymentService.refund(intent.ref, amount_q=3000, reason="item 1")
        PaymentService.refund(intent.ref, amount_q=2000, reason="item 2")

        self.assertEqual(PaymentService.refunded_total(intent.ref), 5000)
        self.assertEqual(PaymentService.captured_total(intent.ref), 10000)

        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentIntent.Status.REFUNDED)

    def test_full_refund_via_partial_steps(self) -> None:
        """Fully refund in multiple steps, then no more refunds allowed."""
        intent = self._captured_intent(10000)

        PaymentService.refund(intent.ref, amount_q=6000)
        PaymentService.refund(intent.ref, amount_q=4000)

        self.assertEqual(PaymentService.refunded_total(intent.ref), 10000)

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.refund(intent.ref, amount_q=1)
        self.assertEqual(ctx.exception.code, "already_refunded")

    def test_refund_exceeds_available_rejected(self) -> None:
        intent = self._captured_intent(10000)
        PaymentService.refund(intent.ref, amount_q=7000)

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.refund(intent.ref, amount_q=5000)
        self.assertEqual(ctx.exception.code, "amount_exceeds_captured")

    def test_default_refund_amount_is_remaining(self) -> None:
        """Omitting amount_q refunds the remaining balance."""
        intent = self._captured_intent(10000)
        PaymentService.refund(intent.ref, amount_q=3000)

        # Default: refund remaining 7000
        txn = PaymentService.refund(intent.ref)
        self.assertEqual(txn.amount_q, 7000)
        self.assertEqual(PaymentService.refunded_total(intent.ref), 10000)

    def test_refunded_status_means_at_least_one_refund(self) -> None:
        """Status REFUNDED after partial refund; balance still positive."""
        intent = self._captured_intent(10000)
        PaymentService.refund(intent.ref, amount_q=1000)

        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentIntent.Status.REFUNDED)
        # But only 1000 was actually refunded
        self.assertEqual(PaymentService.refunded_total(intent.ref), 1000)


class MutationSurfaceContractTests(TestCase):
    """All mutations must go through PaymentService."""

    def test_direct_model_status_change_validates_transitions(self) -> None:
        """Even direct model.save() enforces transition rules."""
        intent = PaymentService.create_intent("ORD-MUT", 5000, "pix")
        intent.status = PaymentIntent.Status.CAPTURED  # skip authorize
        with self.assertRaises(PaymentError) as ctx:
            intent.save()
        self.assertEqual(ctx.exception.code, "invalid_transition")
