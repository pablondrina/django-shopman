"""Gateway reconciliation contracts for Payman."""
from __future__ import annotations

from django.test import TestCase
from shopman.payman.exceptions import PaymentError
from shopman.payman.models import PaymentIntent, PaymentTransaction
from shopman.payman.service import PaymentService


class GatewayReconciliationTests(TestCase):
    def test_captured_snapshot_from_pending_authorizes_and_captures(self) -> None:
        intent = PaymentService.create_intent(
            "ORD-REC-CAP",
            10000,
            "card",
            ref="PAY-REC-CAP",
            gateway="stripe",
            gateway_id="pi_rec_cap",
        )

        result = PaymentService.reconcile_gateway_status(
            intent.ref,
            gateway_status="succeeded",
            amount_q=10000,
            captured_q=10000,
            refunded_q=0,
            gateway_id="pi_rec_cap",
        )

        intent.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertEqual(result.actions, ("authorized", "captured"))
        self.assertEqual(intent.status, PaymentIntent.Status.CAPTURED)
        self.assertEqual(PaymentService.captured_total(intent.ref), 10000)
        self.assertEqual(PaymentTransaction.objects.filter(intent=intent).count(), 1)

        repeat = PaymentService.reconcile_gateway_status(
            intent.ref,
            gateway_status="captured",
            amount_q=10000,
            captured_q=10000,
            refunded_q=0,
            gateway_id="pi_rec_cap",
        )
        self.assertFalse(repeat.changed)
        self.assertEqual(repeat.actions, ())
        self.assertEqual(PaymentTransaction.objects.filter(intent=intent).count(), 1)

    def test_cumulative_refunds_apply_only_new_delta(self) -> None:
        intent = PaymentService.create_intent(
            "ORD-REC-REF",
            10000,
            "card",
            ref="PAY-REC-REF",
            gateway="stripe",
            gateway_id="pi_rec_ref",
        )
        PaymentService.authorize(intent.ref, gateway_id="pi_rec_ref")
        PaymentService.capture(intent.ref, gateway_id="ch_rec_ref")

        first = PaymentService.reconcile_gateway_status(
            intent.ref,
            gateway_status="refunded",
            amount_q=10000,
            captured_q=10000,
            refunded_q=3000,
            gateway_id="pi_rec_ref",
            refund_gateway_id="ch_rec_ref",
        )
        second = PaymentService.reconcile_gateway_status(
            intent.ref,
            gateway_status="refunded",
            amount_q=10000,
            captured_q=10000,
            refunded_q=7000,
            gateway_id="pi_rec_ref",
            refund_gateway_id="ch_rec_ref",
        )
        repeat = PaymentService.reconcile_gateway_status(
            intent.ref,
            gateway_status="refunded",
            amount_q=10000,
            captured_q=10000,
            refunded_q=7000,
            gateway_id="pi_rec_ref",
            refund_gateway_id="ch_rec_ref",
        )

        self.assertEqual(first.actions, ("refunded",))
        self.assertEqual(second.actions, ("refunded",))
        self.assertFalse(repeat.changed)
        self.assertEqual(PaymentService.refunded_total(intent.ref), 7000)
        refunds = list(
            PaymentTransaction.objects.filter(
                intent=intent,
                type=PaymentTransaction.Type.REFUND,
            )
            .order_by("created_at")
            .values_list("amount_q", flat=True)
        )
        self.assertEqual(refunds, [3000, 4000])

    def test_rejects_gateway_refund_below_local_total(self) -> None:
        intent = PaymentService.create_intent("ORD-REC-LOW", 10000, "pix", ref="PAY-REC-LOW")
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        PaymentService.refund(intent.ref, amount_q=5000)

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.reconcile_gateway_status(
                intent.ref,
                gateway_status="refunded",
                amount_q=10000,
                captured_q=10000,
                refunded_q=3000,
            )

        self.assertEqual(ctx.exception.code, "reconciliation_refund_mismatch")

    def test_rejects_gateway_snapshot_that_omits_existing_refund(self) -> None:
        intent = PaymentService.create_intent("ORD-REC-ZERO", 10000, "pix", ref="PAY-REC-ZERO")
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        PaymentService.refund(intent.ref, amount_q=1000)

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.reconcile_gateway_status(
                intent.ref,
                gateway_status="captured",
                amount_q=10000,
                captured_q=10000,
                refunded_q=0,
            )

        self.assertEqual(ctx.exception.code, "reconciliation_refund_mismatch")

    def test_rejects_gateway_capture_after_local_cancel(self) -> None:
        intent = PaymentService.create_intent("ORD-REC-CANCEL", 5000, "pix", ref="PAY-REC-CANCEL")
        PaymentService.cancel(intent.ref)

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.reconcile_gateway_status(
                intent.ref,
                gateway_status="captured",
                amount_q=5000,
                captured_q=5000,
            )

        self.assertEqual(ctx.exception.code, "reconciliation_terminal_drift")

    def test_cancelled_snapshot_cancels_unpaid_intent(self) -> None:
        intent = PaymentService.create_intent("ORD-REC-GW-CANCEL", 5000, "pix", ref="PAY-REC-GW-CANCEL")
        PaymentService.authorize(intent.ref)

        result = PaymentService.reconcile_gateway_status(
            intent.ref,
            gateway_status="cancelled",
            amount_q=5000,
            captured_q=0,
            refunded_q=0,
        )

        intent.refresh_from_db()
        self.assertEqual(result.actions, ("cancelled",))
        self.assertEqual(intent.status, PaymentIntent.Status.CANCELLED)
        self.assertEqual(intent.cancel_reason, "gateway_reconciliation")
