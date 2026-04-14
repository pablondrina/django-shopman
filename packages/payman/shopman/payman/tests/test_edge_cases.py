"""
Edge cases, negative paths, and boundary conditions for Payman.

These tests complement the happy-path coverage in test_service.py and
test_transitions.py by focusing on invalid states, boundary amounts,
expiry behaviour, and record creation guarantees.
"""
from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from shopman.payman.exceptions import PaymentError
from shopman.payman.models import PaymentIntent, PaymentTransaction
from shopman.payman.service import PaymentService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_intent(ref: str, amount_q: int = 5000, method: str = "pix") -> PaymentIntent:
    return PaymentService.create_intent(f"ORD-{ref}", amount_q, method, ref=f"PAY-{ref}")


def _captured_intent(ref: str, amount_q: int = 10000) -> PaymentIntent:
    intent = _make_intent(ref, amount_q)
    PaymentService.authorize(intent.ref)
    PaymentService.capture(intent.ref)
    return PaymentService.get(intent.ref)


# ---------------------------------------------------------------------------
# Invalid transitions
# ---------------------------------------------------------------------------

class InvalidTransitionTests(TestCase):
    """Verify that the FSM rejects transitions that are not in TRANSITIONS."""

    def test_capture_from_failed_raises(self) -> None:
        """intent failed → capture must raise (requires AUTHORIZED status)."""
        intent = _make_intent("FAIL-CAP")
        PaymentService.fail(intent.ref)

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.capture(intent.ref)
        self.assertEqual(ctx.exception.code, "invalid_transition")

    def test_refund_from_pending_raises(self) -> None:
        """intent pending → refund must raise (requires CAPTURED or REFUNDED)."""
        intent = _make_intent("PEND-REF")

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.refund(intent.ref)
        self.assertEqual(ctx.exception.code, "invalid_transition")

    def test_double_capture_raises(self) -> None:
        """intent already captured → second capture must raise."""
        intent = _make_intent("DBL-CAP")
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.capture(intent.ref)
        self.assertEqual(ctx.exception.code, "invalid_transition")

    def test_cancel_after_capture_raises(self) -> None:
        """intent captured → cancel must raise (CAPTURED only allows REFUNDED)."""
        intent = _captured_intent("CAP-CANCEL")

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.cancel(intent.ref)
        self.assertEqual(ctx.exception.code, "invalid_transition")

    def test_refund_from_cancelled_raises(self) -> None:
        """intent cancelled → refund must raise (terminal status, no refund allowed)."""
        intent = _make_intent("CANC-REF")
        PaymentService.cancel(intent.ref)

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.refund(intent.ref)
        self.assertEqual(ctx.exception.code, "invalid_transition")

    def test_authorize_from_captured_raises(self) -> None:
        """intent captured → re-authorize must raise."""
        intent = _captured_intent("CAP-AUTH")

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.authorize(intent.ref)
        self.assertEqual(ctx.exception.code, "invalid_transition")


# ---------------------------------------------------------------------------
# Amount boundary conditions
# ---------------------------------------------------------------------------

class AmountTests(TestCase):
    """Boundary conditions on amount_q values."""

    def test_zero_amount_intent_rejected(self) -> None:
        """amount_q=0 must raise invalid_amount."""
        with self.assertRaises(PaymentError) as ctx:
            PaymentService.create_intent("ORD-ZERO", 0, "pix")
        self.assertEqual(ctx.exception.code, "invalid_amount")

    def test_negative_amount_intent_rejected(self) -> None:
        """amount_q<0 must raise invalid_amount."""
        with self.assertRaises(PaymentError) as ctx:
            PaymentService.create_intent("ORD-NEG", -1, "pix")
        self.assertEqual(ctx.exception.code, "invalid_amount")

    def test_refund_amount_exceeds_captured(self) -> None:
        """Refund larger than the captured amount must raise amount_exceeds_captured."""
        intent = _captured_intent("REF-EXCEED")

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.refund(intent.ref, amount_q=intent.amount_q + 1)
        self.assertEqual(ctx.exception.code, "amount_exceeds_captured")

    def test_partial_refund_tracking(self) -> None:
        """After a partial refund the remaining available amount is correct."""
        amount = 10000
        intent = _captured_intent("PARTIAL-TRK", amount_q=amount)

        first_refund = 3000
        PaymentService.refund(intent.ref, amount_q=first_refund)

        refunded = PaymentService.refunded_total(intent.ref)
        captured = PaymentService.captured_total(intent.ref)
        remaining = captured - refunded

        self.assertEqual(refunded, first_refund)
        self.assertEqual(remaining, amount - first_refund)

        # Second refund for exactly the remaining amount must succeed
        txn2 = PaymentService.refund(intent.ref, amount_q=remaining)
        self.assertEqual(txn2.amount_q, remaining)
        self.assertEqual(PaymentService.refunded_total(intent.ref), amount)

    def test_partial_refund_then_overshoot_raises(self) -> None:
        """After a partial refund, attempting to refund more than the remainder raises."""
        intent = _captured_intent("PARTIAL-OVER")
        PaymentService.refund(intent.ref, amount_q=6000)

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.refund(intent.ref, amount_q=5000)  # only 4000 left
        self.assertEqual(ctx.exception.code, "amount_exceeds_captured")

    def test_minimum_valid_amount(self) -> None:
        """amount_q=1 (one centavo) is the minimum valid amount."""
        intent = PaymentService.create_intent("ORD-MIN", 1, "pix")
        self.assertEqual(intent.amount_q, 1)
        self.assertEqual(intent.status, PaymentIntent.Status.PENDING)


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------

class ExpiryTests(TestCase):
    """PaymentService._check_not_expired is called during authorize only."""

    def test_intent_expired_cannot_be_authorized(self) -> None:
        """An intent with expires_at in the past must raise intent_expired on authorize."""
        past = timezone.now() - timedelta(seconds=1)
        intent = PaymentService.create_intent(
            "ORD-EXP-AUTH", 5000, "pix", expires_at=past,
        )

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.authorize(intent.ref)
        self.assertEqual(ctx.exception.code, "intent_expired")

    def test_non_expired_intent_authorizes_normally(self) -> None:
        """An intent with expires_at in the future must authorize without error."""
        future = timezone.now() + timedelta(minutes=30)
        intent = PaymentService.create_intent(
            "ORD-EXP-OK", 5000, "pix", expires_at=future,
        )
        result = PaymentService.authorize(intent.ref)
        self.assertEqual(result.status, PaymentIntent.Status.AUTHORIZED)

    def test_intent_without_expiry_always_authorizes(self) -> None:
        """An intent without expires_at is never considered expired."""
        intent = PaymentService.create_intent("ORD-NO-EXP", 5000, "pix")
        self.assertIsNone(intent.expires_at)
        result = PaymentService.authorize(intent.ref)
        self.assertEqual(result.status, PaymentIntent.Status.AUTHORIZED)


# ---------------------------------------------------------------------------
# Transaction record guarantees
# ---------------------------------------------------------------------------

class TransactionRecordTests(TestCase):
    """PaymentTransaction records are created for capture and refund operations."""

    def test_transaction_created_on_capture(self) -> None:
        """capture() must create exactly one CAPTURE transaction linked to the intent."""
        intent = _make_intent("TXN-CAP")
        PaymentService.authorize(intent.ref)
        txn = PaymentService.capture(intent.ref)

        self.assertIsInstance(txn, PaymentTransaction)
        self.assertEqual(txn.type, PaymentTransaction.Type.CAPTURE)
        self.assertEqual(txn.intent_id, intent.id)
        self.assertEqual(txn.amount_q, intent.amount_q)

        db_count = PaymentTransaction.objects.filter(
            intent=intent, type=PaymentTransaction.Type.CAPTURE,
        ).count()
        self.assertEqual(db_count, 1)

    def test_transaction_created_on_refund(self) -> None:
        """refund() must create exactly one REFUND transaction linked to the intent."""
        intent = _captured_intent("TXN-REF")
        refund_amount = 4000
        txn = PaymentService.refund(intent.ref, amount_q=refund_amount)

        self.assertIsInstance(txn, PaymentTransaction)
        self.assertEqual(txn.type, PaymentTransaction.Type.REFUND)
        self.assertEqual(txn.intent_id, intent.id)
        self.assertEqual(txn.amount_q, refund_amount)

        db_count = PaymentTransaction.objects.filter(
            intent=intent, type=PaymentTransaction.Type.REFUND,
        ).count()
        self.assertEqual(db_count, 1)

    def test_partial_refunds_create_separate_transactions(self) -> None:
        """Each partial refund call creates a distinct REFUND transaction record."""
        intent = _captured_intent("TXN-MULTI-REF", amount_q=12000)
        PaymentService.refund(intent.ref, amount_q=4000)
        PaymentService.refund(intent.ref, amount_q=8000)

        refund_txns = list(
            PaymentTransaction.objects.filter(
                intent=intent, type=PaymentTransaction.Type.REFUND,
            ).order_by("created_at")
        )
        self.assertEqual(len(refund_txns), 2)
        self.assertEqual(refund_txns[0].amount_q, 4000)
        self.assertEqual(refund_txns[1].amount_q, 8000)

    def test_capture_with_gateway_id_stored(self) -> None:
        """gateway_id passed to capture() is persisted on the transaction."""
        intent = _make_intent("TXN-GW-CAP")
        PaymentService.authorize(intent.ref)
        txn = PaymentService.capture(intent.ref, gateway_id="ch_abc123")

        self.assertEqual(txn.gateway_id, "ch_abc123")
        txn.refresh_from_db()
        self.assertEqual(txn.gateway_id, "ch_abc123")


# ---------------------------------------------------------------------------
# Status timestamp fields
# ---------------------------------------------------------------------------

class StatusTimestampTests(TestCase):
    """Verify that the correct timestamp fields are set on each transition."""

    def test_authorized_at_set_on_authorize(self) -> None:
        intent = _make_intent("TS-AUTH")
        self.assertIsNone(intent.authorized_at)

        PaymentService.authorize(intent.ref)
        intent.refresh_from_db()
        self.assertIsNotNone(intent.authorized_at)

    def test_captured_at_set_on_capture(self) -> None:
        intent = _make_intent("TS-CAP")
        PaymentService.authorize(intent.ref)
        self.assertIsNone(PaymentService.get(intent.ref).captured_at)

        PaymentService.capture(intent.ref)
        intent.refresh_from_db()
        self.assertIsNotNone(intent.captured_at)

    def test_cancelled_at_set_on_cancel(self) -> None:
        intent = _make_intent("TS-CANC")
        self.assertIsNone(intent.cancelled_at)

        PaymentService.cancel(intent.ref)
        intent.refresh_from_db()
        self.assertIsNotNone(intent.cancelled_at)

    def test_timestamp_not_overwritten_if_already_set(self) -> None:
        """If a timestamp field is already populated, save() must not overwrite it."""
        intent = _make_intent("TS-NOOW")
        early = timezone.now() - timedelta(hours=2)
        # Directly assign a past timestamp before transitioning
        PaymentIntent.objects.filter(pk=intent.pk).update(authorized_at=early)
        intent.refresh_from_db()

        # Transitioning to AUTHORIZED should not overwrite the existing timestamp
        intent.status = PaymentIntent.Status.AUTHORIZED
        intent.save()
        intent.refresh_from_db()
        self.assertEqual(
            intent.authorized_at.replace(microsecond=0),
            early.replace(microsecond=0),
        )

    def test_failed_has_no_dedicated_timestamp_field(self) -> None:
        """FAILED is not in STATUS_TIMESTAMP_FIELDS — no dedicated timestamp is set."""
        self.assertNotIn(
            PaymentIntent.Status.FAILED,
            PaymentIntent.STATUS_TIMESTAMP_FIELDS,
        )

    def test_refunded_has_no_dedicated_timestamp_field(self) -> None:
        """REFUNDED is not in STATUS_TIMESTAMP_FIELDS — no dedicated timestamp is set."""
        self.assertNotIn(
            PaymentIntent.Status.REFUNDED,
            PaymentIntent.STATUS_TIMESTAMP_FIELDS,
        )


# ---------------------------------------------------------------------------
# _original_status tracking
# ---------------------------------------------------------------------------

class OriginalStatusTrackingTests(TestCase):
    """_original_status reflects the persisted status, not the in-memory pending change."""

    def test_original_status_is_pending_on_creation(self) -> None:
        intent = _make_intent("ORIG-PEND")
        self.assertEqual(intent._original_status, PaymentIntent.Status.PENDING)

    def test_original_status_updated_after_save(self) -> None:
        """_original_status is synced by save() on the same object, not via refresh_from_db().
        Django's refresh_from_db() bypasses __init__, so _original_status is NOT updated by it.
        Fetch a fresh instance from the DB to get the correctly initialised _original_status."""
        intent = _make_intent("ORIG-SAVE")
        # authorize() operates on a locked copy; fetch a fresh instance to observe _original_status
        PaymentService.authorize(intent.ref)
        fresh = PaymentIntent.objects.get(ref=intent.ref)
        self.assertEqual(fresh.status, PaymentIntent.Status.AUTHORIZED)
        self.assertEqual(fresh._original_status, PaymentIntent.Status.AUTHORIZED)

    def test_original_status_updated_via_transition_status(self) -> None:
        """transition_status() syncs _original_status on the calling instance."""
        intent = _make_intent("ORIG-TRANS")
        intent.transition_status(PaymentIntent.Status.AUTHORIZED)
        self.assertEqual(intent._original_status, PaymentIntent.Status.AUTHORIZED)
        self.assertEqual(intent.status, PaymentIntent.Status.AUTHORIZED)

    def test_original_status_prevents_repeated_invalid_save(self) -> None:
        """After a failed transition attempt, _original_status is unchanged."""
        intent = _make_intent("ORIG-FAIL")
        # Attempt invalid transition (pending → captured)
        intent.status = PaymentIntent.Status.CAPTURED
        with self.assertRaises(PaymentError):
            intent.save()
        # _original_status should still reflect the last saved state (pending)
        self.assertEqual(intent._original_status, PaymentIntent.Status.PENDING)
