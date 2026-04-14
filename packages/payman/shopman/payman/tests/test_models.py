"""Tests for Payment models — creation, constraints, __str__."""
from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from shopman.payman.models import PaymentIntent, PaymentTransaction


class PaymentIntentCreationTests(TestCase):
    def test_create_intent(self) -> None:
        intent = PaymentIntent.objects.create(
            ref="PAY-001",
            order_ref="ORD-001",
            method="pix",
            amount_q=5000,
        )
        self.assertEqual(intent.status, "pending")
        self.assertEqual(intent.currency, "BRL")
        self.assertEqual(intent.amount_q, 5000)
        self.assertIsNotNone(intent.created_at)

    def test_str(self) -> None:
        intent = PaymentIntent.objects.create(
            ref="PAY-002", order_ref="ORD-002", method="card", amount_q=1500,
        )
        self.assertEqual(str(intent), "PAY-002 (card/pending)")

    def test_ref_unique(self) -> None:
        PaymentIntent.objects.create(
            ref="PAY-DUP", order_ref="ORD-001", method="pix", amount_q=1000,
        )
        with self.assertRaises(Exception):
            PaymentIntent.objects.create(
                ref="PAY-DUP", order_ref="ORD-002", method="pix", amount_q=2000,
            )

    def test_multiple_intents_per_order(self) -> None:
        PaymentIntent.objects.create(
            ref="PAY-A", order_ref="ORD-MULTI", method="pix", amount_q=3000,
        )
        PaymentIntent.objects.create(
            ref="PAY-B", order_ref="ORD-MULTI", method="card", amount_q=2000,
        )
        self.assertEqual(
            PaymentIntent.objects.filter(order_ref="ORD-MULTI").count(), 2,
        )

    def test_gateway_data_json(self) -> None:
        intent = PaymentIntent.objects.create(
            ref="PAY-GW", order_ref="ORD-GW", method="pix", amount_q=1000,
            gateway="efi", gateway_id="txid_abc123",
            gateway_data={"qr_code": "00020126...", "location": "https://pix.example.com"},
        )
        intent.refresh_from_db()
        self.assertEqual(intent.gateway_data["qr_code"], "00020126...")

    def test_expires_at(self) -> None:
        expires = timezone.now() + timedelta(minutes=30)
        intent = PaymentIntent.objects.create(
            ref="PAY-EXP", order_ref="ORD-EXP", method="pix",
            amount_q=2000, expires_at=expires,
        )
        intent.refresh_from_db()
        self.assertIsNotNone(intent.expires_at)

    def test_is_terminal(self) -> None:
        intent = PaymentIntent.objects.create(
            ref="PAY-TERM", order_ref="ORD-T", method="pix", amount_q=1000,
        )
        self.assertFalse(intent.is_terminal)

        intent.status = PaymentIntent.Status.CANCELLED
        intent.save()
        self.assertTrue(intent.is_terminal)

    def test_default_gateway_fields(self) -> None:
        intent = PaymentIntent.objects.create(
            ref="PAY-DEF", order_ref="ORD-DEF", method="pix", amount_q=1000,
        )
        self.assertEqual(intent.gateway, "")
        self.assertEqual(intent.gateway_id, "")
        self.assertEqual(intent.gateway_data, {})


class PaymentTransactionCreationTests(TestCase):
    def setUp(self) -> None:
        self.intent = PaymentIntent.objects.create(
            ref="PAY-TXN", order_ref="ORD-TXN", method="pix", amount_q=10000,
        )
        # Advance to captured for transaction tests
        self.intent.status = PaymentIntent.Status.AUTHORIZED
        self.intent.save()
        self.intent.status = PaymentIntent.Status.CAPTURED
        self.intent.save()

    def test_create_capture_transaction(self) -> None:
        txn = PaymentTransaction.objects.create(
            intent=self.intent, type="capture", amount_q=10000, gateway_id="cap_123",
        )
        self.assertEqual(txn.amount_q, 10000)
        self.assertEqual(txn.intent, self.intent)
        self.assertIsNotNone(txn.created_at)

    def test_create_refund_transaction(self) -> None:
        txn = PaymentTransaction.objects.create(
            intent=self.intent, type="refund", amount_q=5000, gateway_id="ref_456",
        )
        self.assertEqual(txn.type, "refund")
        self.assertEqual(txn.amount_q, 5000)

    def test_partial_refunds(self) -> None:
        PaymentTransaction.objects.create(
            intent=self.intent, type="refund", amount_q=3000,
        )
        PaymentTransaction.objects.create(
            intent=self.intent, type="refund", amount_q=2000,
        )
        total_refunded = sum(
            t.amount_q for t in self.intent.transactions.filter(type="refund")
        )
        self.assertEqual(total_refunded, 5000)

    def test_str(self) -> None:
        txn = PaymentTransaction.objects.create(
            intent=self.intent, type="capture", amount_q=10000,
        )
        self.assertIn("capture", str(txn))
        self.assertIn("10000", str(txn))

    def test_protect_delete(self) -> None:
        PaymentTransaction.objects.create(
            intent=self.intent, type="capture", amount_q=10000,
        )
        with self.assertRaises(Exception):
            self.intent.delete()

    def test_chargeback_transaction(self) -> None:
        txn = PaymentTransaction.objects.create(
            intent=self.intent, type="chargeback", amount_q=10000, gateway_id="cb_789",
        )
        self.assertEqual(txn.type, "chargeback")
