"""
HP2-06 Hardening tests — 4 drift fixes.

1. get_active_intent() excludes expired intents.
2. gateway_id unique constraint (gateway, gateway_id) WHERE gateway_id != ''.
3. PaymentTransaction QuerySet mutation guards.
4. cancel() reason persisted to cancel_reason field.
"""
from __future__ import annotations

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from shopman.payman.models import PaymentIntent, PaymentTransaction
from shopman.payman.service import PaymentService


def _make_intent(ref: str, **kwargs) -> PaymentIntent:
    return PaymentService.create_intent(f"ORD-{ref}", 5000, "pix", ref=f"PAY-{ref}", **kwargs)


# ---------------------------------------------------------------------------
# Fix 1 — get_active_intent() excludes expired intents
# ---------------------------------------------------------------------------

class GetActiveIntentExpiryTests(TestCase):
    """get_active_intent() must not return expired intents, even if non-terminal."""

    def test_active_intent_without_expiry_returned(self) -> None:
        _make_intent("ACT-NOEXP")
        result = PaymentService.get_active_intent("ORD-ACT-NOEXP")
        self.assertIsNotNone(result)

    def test_active_intent_with_future_expiry_returned(self) -> None:
        future = timezone.now() + timedelta(minutes=30)
        _make_intent("ACT-FUTEXP", expires_at=future)
        result = PaymentService.get_active_intent("ORD-ACT-FUTEXP")
        self.assertIsNotNone(result)

    def test_expired_intent_not_returned(self) -> None:
        past = timezone.now() - timedelta(seconds=1)
        _make_intent("ACT-PASTEXP", expires_at=past)
        result = PaymentService.get_active_intent("ORD-ACT-PASTEXP")
        self.assertIsNone(result)

    def test_expired_intent_ignored_even_if_pending(self) -> None:
        """PENDING + expired must not be returned (previously it would be)."""
        past = timezone.now() - timedelta(hours=1)
        intent = _make_intent("ACT-PENDEXP", expires_at=past)
        self.assertEqual(intent.status, PaymentIntent.Status.PENDING)

        result = PaymentService.get_active_intent("ORD-ACT-PENDEXP")
        self.assertIsNone(result)

    def test_fresh_intent_returned_when_expired_one_also_exists(self) -> None:
        """The non-expired intent wins over the expired one for the same order."""
        past = timezone.now() - timedelta(hours=1)
        PaymentService.create_intent("ORD-ACT-MIXED", 5000, "pix", ref="PAY-OLD-EXP", expires_at=past)
        PaymentService.create_intent("ORD-ACT-MIXED", 5000, "pix", ref="PAY-NEW-OK")

        result = PaymentService.get_active_intent("ORD-ACT-MIXED")
        self.assertIsNotNone(result)
        self.assertEqual(result.ref, "PAY-NEW-OK")

    def test_terminal_status_still_excluded(self) -> None:
        """Cancelled intent still excluded (terminal, regardless of expiry)."""
        intent = _make_intent("ACT-TERM")
        PaymentService.cancel(intent.ref)
        self.assertIsNone(PaymentService.get_active_intent("ORD-ACT-TERM"))


# ---------------------------------------------------------------------------
# Fix 2 — gateway_id unique constraint
# ---------------------------------------------------------------------------

class GatewayIdUniqueTests(TestCase):
    """UniqueConstraint(gateway, gateway_id) WHERE gateway_id != '' prevents duplicates."""

    def test_same_gateway_id_same_gateway_raises(self) -> None:
        PaymentService.create_intent(
            "ORD-GW-A", 5000, "pix", ref="PAY-GW-A",
            gateway="efi", gateway_id="txid_001",
        )
        with self.assertRaises((IntegrityError, Exception)):
            with transaction.atomic():
                PaymentService.create_intent(
                    "ORD-GW-B", 5000, "pix", ref="PAY-GW-B",
                    gateway="efi", gateway_id="txid_001",
                )

    def test_same_gateway_id_different_gateway_allowed(self) -> None:
        PaymentService.create_intent(
            "ORD-GW-C", 5000, "pix", ref="PAY-GW-C",
            gateway="efi", gateway_id="txid_shared",
        )
        intent2 = PaymentService.create_intent(
            "ORD-GW-D", 5000, "pix", ref="PAY-GW-D",
            gateway="stripe", gateway_id="txid_shared",
        )
        self.assertEqual(intent2.gateway_id, "txid_shared")

    def test_get_by_gateway_id_can_scope_by_gateway(self) -> None:
        efi = PaymentService.create_intent(
            "ORD-GW-I", 5000, "pix", ref="PAY-GW-I",
            gateway="efi", gateway_id="txid_lookup",
        )
        stripe = PaymentService.create_intent(
            "ORD-GW-J", 5000, "card", ref="PAY-GW-J",
            gateway="stripe", gateway_id="txid_lookup",
        )

        self.assertEqual(PaymentService.get_by_gateway_id("txid_lookup", gateway="efi"), efi)
        self.assertEqual(PaymentService.get_by_gateway_id("txid_lookup", gateway="stripe"), stripe)

    def test_empty_gateway_id_allows_duplicates(self) -> None:
        """Constraint is conditional: empty gateway_id rows are not constrained."""
        PaymentService.create_intent("ORD-GW-E", 5000, "pix", ref="PAY-GW-E", gateway="efi")
        intent2 = PaymentService.create_intent("ORD-GW-F", 5000, "pix", ref="PAY-GW-F", gateway="efi")
        self.assertEqual(intent2.gateway_id, "")

    def test_different_gateway_id_same_gateway_allowed(self) -> None:
        PaymentService.create_intent(
            "ORD-GW-G", 5000, "pix", ref="PAY-GW-G",
            gateway="efi", gateway_id="txid_111",
        )
        intent2 = PaymentService.create_intent(
            "ORD-GW-H", 5000, "pix", ref="PAY-GW-H",
            gateway="efi", gateway_id="txid_222",
        )
        self.assertEqual(intent2.gateway_id, "txid_222")


# ---------------------------------------------------------------------------
# Fix 3 — PaymentTransaction QuerySet.update() guard
# ---------------------------------------------------------------------------

class TransactionQuerySetGuardTests(TestCase):
    """PaymentTransaction.objects.update() must raise to protect immutability."""

    def setUp(self) -> None:
        intent = PaymentService.create_intent("ORD-TXN-GUARD", 10000, "pix", ref="PAY-TXN-GUARD")
        PaymentService.authorize(intent.ref)
        self.txn = PaymentService.capture(intent.ref)

    def test_update_via_queryset_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            PaymentTransaction.objects.filter(pk=self.txn.pk).update(amount_q=1)
        self.assertIn("imutáv", str(ctx.exception).lower())

    def test_update_all_raises(self) -> None:
        with self.assertRaises(ValueError):
            PaymentTransaction.objects.update(gateway_id="tampered")

    def test_delete_via_queryset_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            PaymentTransaction.objects.filter(pk=self.txn.pk).delete()
        self.assertIn("imutáv", str(ctx.exception).lower())

    def test_save_on_existing_raises(self) -> None:
        """save() on an existing record is also guarded."""
        self.txn.gateway_id = "tampered"
        with self.assertRaises(ValueError):
            self.txn.save()

    def test_create_still_works(self) -> None:
        """objects.create() goes through save() (pk=None) — must still work."""
        intent = PaymentService.get("PAY-TXN-GUARD")
        txn = PaymentTransaction.objects.create(
            intent=intent, type="refund", amount_q=5000,
        )
        self.assertIsNotNone(txn.pk)


# ---------------------------------------------------------------------------
# Fix 4 — cancel() reason persisted
# ---------------------------------------------------------------------------

class CancelReasonTests(TestCase):
    """cancel(reason=...) must persist the reason to intent.cancel_reason."""

    def test_cancel_reason_persisted(self) -> None:
        intent = _make_intent("CANC-RSN-1")
        PaymentService.cancel(intent.ref, reason="customer_requested")

        intent.refresh_from_db()
        self.assertEqual(intent.cancel_reason, "customer_requested")

    def test_cancel_without_reason_stores_empty_string(self) -> None:
        intent = _make_intent("CANC-RSN-2")
        PaymentService.cancel(intent.ref)

        intent.refresh_from_db()
        self.assertEqual(intent.cancel_reason, "")

    def test_cancel_reason_field_exists_on_model(self) -> None:
        intent = _make_intent("CANC-RSN-3")
        self.assertTrue(hasattr(intent, "cancel_reason"))
        self.assertEqual(intent.cancel_reason, "")

    def test_cancel_reason_readable_after_cancel(self) -> None:
        intent = _make_intent("CANC-RSN-4")
        result = PaymentService.cancel(intent.ref, reason="payment_gateway_timeout")
        result.refresh_from_db()
        self.assertEqual(result.cancel_reason, "payment_gateway_timeout")

    def test_cancel_reason_accepts_gateway_diagnostic_context(self) -> None:
        reason = "x" * 500
        intent = _make_intent("CANC-RSN-LONG")
        PaymentService.cancel(intent.ref, reason=reason)

        intent.refresh_from_db()
        self.assertEqual(intent.cancel_reason, reason)

    def test_cancel_reason_stored_from_authorized_status(self) -> None:
        """cancel() from AUTHORIZED status also persists the reason."""
        intent = _make_intent("CANC-RSN-5")
        PaymentService.authorize(intent.ref)
        PaymentService.cancel(intent.ref, reason="fraud_detected")

        intent.refresh_from_db()
        self.assertEqual(intent.cancel_reason, "fraud_detected")
