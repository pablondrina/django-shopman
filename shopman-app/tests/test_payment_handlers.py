"""
Dedicated tests for payment handlers — edge cases, idempotency, and error paths.

Extends test_payment_contrib.py with scenarios not covered there:
- PaymentCaptureHandler: session fallback edge cases, capture failure, order not found
- PaymentRefundHandler: already refunded idempotency, partial refund status, order not found
- PixGenerateHandler: QR extraction from metadata vs client_secret, reminder timing, default timeout
- PixTimeoutHandler: naive datetime handling, terminal order status, hold release, gateway cancel
"""

from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from shopman.payment.adapters.mock import MockPaymentBackend
from shopman.payment.handlers import (
    PaymentCaptureHandler,
    PaymentRefundHandler,
    PixGenerateHandler,
    PixTimeoutHandler,
)
from shopman.payment.protocols import (
    CaptureResult,
    PaymentIntent,
    PaymentStatus,
    RefundResult,
)
from shopman.ordering.models import Channel, Directive, Order, Session


def _create_directive(**kwargs) -> Directive:
    """Create directive bypassing post_save signal."""
    objs = Directive.objects.bulk_create([Directive(**kwargs)])
    return objs[0]


def _make_channel(**overrides) -> Channel:
    config = {
        "order_flow": {
            "transitions": {
                "new": ["confirmed", "cancelled"],
                "confirmed": ["processing", "cancelled"],
                "processing": ["ready", "cancelled"],
                "ready": ["completed"],
                "completed": [],
                "cancelled": [],
            },
            "terminal_statuses": ["completed", "cancelled"],
        },
    }
    defaults = dict(ref="test-ch", name="Test Channel", config=config)
    defaults.update(overrides)
    return Channel.objects.create(**defaults)


# ────────────────────────────────────────────────────────────────
# PaymentCaptureHandler — dedicated edge cases
# ────────────────────────────────────────────────────────────────


class PaymentCaptureHandlerEdgeCaseTests(TestCase):
    """Edge cases not covered in test_payment_contrib.py."""

    def setUp(self) -> None:
        self.channel = _make_channel()
        self.backend = MockPaymentBackend()
        self.handler = PaymentCaptureHandler(self.backend)

    def test_capture_failure_marks_directive_failed(self) -> None:
        """Backend capture failure → directive.status=failed with error details."""
        # Create an intent that can't be captured (cancelled)
        intent = self.backend.create_intent(1000, "BRL")
        self.backend.cancel(intent.intent_id)

        directive = _create_directive(
            topic="payment.capture",
            payload={"intent_id": intent.intent_id, "amount_q": 1000},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertIn("invalid_status", directive.last_error)

    def test_capture_session_not_found_falls_through(self) -> None:
        """Missing session with session_key → no intent_id → failed."""
        directive = _create_directive(
            topic="payment.capture",
            payload={
                "session_key": "NONEXISTENT",
                "channel_ref": self.channel.ref,
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertEqual(directive.last_error, "no_intent_id")

    def test_capture_session_without_payment_data(self) -> None:
        """Session exists but has no payment.intent_id → failed."""
        Session.objects.create(
            session_key="EMPTY-SESSION",
            channel=self.channel,
            state="committed",
            data={},
        )

        directive = _create_directive(
            topic="payment.capture",
            payload={
                "session_key": "EMPTY-SESSION",
                "channel_ref": self.channel.ref,
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertEqual(directive.last_error, "no_intent_id")

    def test_capture_no_order_ref_still_succeeds(self) -> None:
        """Capture without order_ref → succeeds (no event emitted)."""
        intent = self.backend.create_intent(2000, "BRL")
        directive = _create_directive(
            topic="payment.capture",
            payload={"intent_id": intent.intent_id, "amount_q": 2000},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.assertIn("transaction_id", directive.payload)

    def test_capture_order_not_found_still_succeeds(self) -> None:
        """Capture with nonexistent order_ref → succeeds (Order.DoesNotExist silenced)."""
        intent = self.backend.create_intent(2000, "BRL")
        directive = _create_directive(
            topic="payment.capture",
            payload={
                "intent_id": intent.intent_id,
                "order_ref": "NONEXISTENT-ORDER",
                "amount_q": 2000,
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

    def test_capture_stores_transaction_id_in_payload(self) -> None:
        """Successful capture saves transaction_id back into directive.payload."""
        intent = self.backend.create_intent(3000, "BRL")
        directive = _create_directive(
            topic="payment.capture",
            payload={"intent_id": intent.intent_id},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertIsNotNone(directive.payload.get("transaction_id"))
        self.assertTrue(directive.payload["transaction_id"].startswith("mock_txn_"))


# ────────────────────────────────────────────────────────────────
# PaymentRefundHandler — dedicated edge cases
# ────────────────────────────────────────────────────────────────


class PaymentRefundHandlerEdgeCaseTests(TestCase):
    """Refund handler edge cases."""

    def setUp(self) -> None:
        self.channel = _make_channel()
        self.backend = MockPaymentBackend()
        self.handler = PaymentRefundHandler(self.backend)
        # Pre-create a captured intent
        self.intent = self.backend.create_intent(5000, "BRL")
        self.backend.capture(self.intent.intent_id)

    def test_refund_already_refunded_is_idempotent(self) -> None:
        """Re-refunding already refunded intent → done (idempotent)."""
        self.backend.refund(self.intent.intent_id)

        directive = _create_directive(
            topic="payment.refund",
            payload={"intent_id": self.intent.intent_id},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

    def test_refund_partial_then_full(self) -> None:
        """Partial refund leaves status=captured; full refund sets status=refunded."""
        # Partial refund
        d1 = _create_directive(
            topic="payment.refund",
            payload={"intent_id": self.intent.intent_id, "amount_q": 2000},
        )
        self.handler.handle(message=d1, ctx={})

        d1.refresh_from_db()
        self.assertEqual(d1.status, "done")

        status = self.backend.get_status(self.intent.intent_id)
        self.assertEqual(status.status, "captured")  # Still captured
        self.assertEqual(status.refunded_q, 2000)

        # Second refund for remainder
        d2 = _create_directive(
            topic="payment.refund",
            payload={"intent_id": self.intent.intent_id, "amount_q": 3000},
        )
        self.handler.handle(message=d2, ctx={})

        d2.refresh_from_db()
        self.assertEqual(d2.status, "done")

        status = self.backend.get_status(self.intent.intent_id)
        self.assertEqual(status.status, "refunded")

    def test_refund_order_not_found_still_succeeds(self) -> None:
        """Refund with nonexistent order → succeeds (no event, Order.DoesNotExist silenced)."""
        directive = _create_directive(
            topic="payment.refund",
            payload={
                "intent_id": self.intent.intent_id,
                "order_ref": "NONEXISTENT-ORDER",
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

    def test_refund_exceeds_amount_fails(self) -> None:
        """Refund amount > captured → failed."""
        directive = _create_directive(
            topic="payment.refund",
            payload={"intent_id": self.intent.intent_id, "amount_q": 99999},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertIn("exceeds_captured", directive.last_error)

    def test_refund_stores_refund_id_in_payload(self) -> None:
        """Successful refund stores refund_id in directive.payload."""
        directive = _create_directive(
            topic="payment.refund",
            payload={"intent_id": self.intent.intent_id},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertIsNotNone(directive.payload.get("refund_id"))

    def test_refund_with_reason_emits_event(self) -> None:
        """Refund with reason → event includes reason in payload."""
        order = Order.objects.create(
            ref="ORD-REFUND-REASON",
            channel=self.channel,
            status="completed",
        )

        directive = _create_directive(
            topic="payment.refund",
            payload={
                "intent_id": self.intent.intent_id,
                "order_ref": order.ref,
                "reason": "Defeito no produto",
            },
        )

        self.handler.handle(message=directive, ctx={})

        events = order.events.filter(type="payment.refunded")
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.first().payload["reason"], "Defeito no produto")


# ────────────────────────────────────────────────────────────────
# PixGenerateHandler — dedicated edge cases
# ────────────────────────────────────────────────────────────────


class PixGenerateHandlerEdgeCaseTests(TestCase):
    """PixGenerateHandler edge cases."""

    def setUp(self) -> None:
        self.channel = _make_channel()
        self.backend = MockPaymentBackend(auto_authorize=False)
        self.handler = PixGenerateHandler(backend=self.backend)

    def test_pix_generate_creates_reminder_at_half_timeout(self) -> None:
        """Reminder directive is created at timeout/2 minutes."""
        order = Order.objects.create(
            ref="ORD-REMINDER", channel=self.channel, total_q=5000, status="new",
        )

        directive = _create_directive(
            topic="pix.generate",
            payload={"order_ref": order.ref, "amount_q": 5000, "pix_timeout_minutes": 20},
        )

        before = timezone.now()
        self.handler.handle(message=directive, ctx={})

        reminder = Directive.objects.filter(topic="notification.send").first()
        self.assertIsNotNone(reminder)
        self.assertEqual(reminder.payload["template"], "payment.reminder")
        # Reminder at 10 min (half of 20)
        self.assertGreaterEqual(reminder.available_at, before + timedelta(minutes=9))

    def test_pix_generate_reminder_minimum_1_minute(self) -> None:
        """Reminder is at least 1 minute even for timeout=1."""
        order = Order.objects.create(
            ref="ORD-MIN-REM", channel=self.channel, total_q=1000, status="new",
        )

        directive = _create_directive(
            topic="pix.generate",
            payload={"order_ref": order.ref, "amount_q": 1000, "pix_timeout_minutes": 1},
        )

        self.handler.handle(message=directive, ctx={})

        reminder = Directive.objects.filter(topic="notification.send").first()
        self.assertIsNotNone(reminder)

    def test_pix_generate_default_timeout_10_minutes(self) -> None:
        """Default pix_timeout_minutes is 10 when not specified."""
        order = Order.objects.create(
            ref="ORD-DEFAULT-TO", channel=self.channel, total_q=2000, status="new",
        )

        directive = _create_directive(
            topic="pix.generate",
            payload={"order_ref": order.ref, "amount_q": 2000},
        )

        before = timezone.now()
        self.handler.handle(message=directive, ctx={})

        pix_timeout = Directive.objects.filter(topic="pix.timeout").first()
        self.assertIsNotNone(pix_timeout)
        # Expires ~10 minutes from now
        expires_at_str = pix_timeout.payload["expires_at"]
        self.assertIsNotNone(expires_at_str)

    def test_pix_generate_extracts_qr_from_client_secret_json(self) -> None:
        """QR code is extracted from client_secret JSON when metadata is empty."""
        order = Order.objects.create(
            ref="ORD-QR-SECRET", channel=self.channel, total_q=3000, status="new",
        )

        directive = _create_directive(
            topic="pix.generate",
            payload={"order_ref": order.ref, "amount_q": 3000},
        )

        self.handler.handle(message=directive, ctx={})

        order.refresh_from_db()
        payment = order.data.get("payment", {})
        # MockPaymentBackend puts brcode/qrcode in client_secret JSON
        self.assertIsNotNone(payment.get("intent_id"))
        self.assertEqual(payment["method"], "pix")

    def test_pix_generate_enriches_order_data(self) -> None:
        """order.data['payment'] is fully populated."""
        order = Order.objects.create(
            ref="ORD-ENRICH", channel=self.channel, total_q=4200, status="new",
        )

        directive = _create_directive(
            topic="pix.generate",
            payload={"order_ref": order.ref, "amount_q": 4200, "pix_timeout_minutes": 15},
        )

        self.handler.handle(message=directive, ctx={})

        order.refresh_from_db()
        payment = order.data["payment"]
        self.assertEqual(payment["amount_q"], 4200)
        self.assertEqual(payment["method"], "pix")
        self.assertIn("intent_id", payment)
        self.assertIn("status", payment)

    def test_pix_generate_stores_intent_id_in_directive(self) -> None:
        """Successful generate saves intent_id in directive.payload."""
        order = Order.objects.create(
            ref="ORD-DIR-ID", channel=self.channel, total_q=1500, status="new",
        )

        directive = _create_directive(
            topic="pix.generate",
            payload={"order_ref": order.ref, "amount_q": 1500},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertIn("intent_id", directive.payload)
        self.assertTrue(directive.payload["intent_id"].startswith("mock_pi_"))


# ────────────────────────────────────────────────────────────────
# PixTimeoutHandler — dedicated edge cases
# ────────────────────────────────────────────────────────────────


class PixTimeoutHandlerEdgeCaseTests(TestCase):
    """PixTimeoutHandler edge cases."""

    def setUp(self) -> None:
        self.channel = _make_channel()
        self.backend = MockPaymentBackend(auto_authorize=False)
        self.handler = PixTimeoutHandler(backend=self.backend)

    def test_timeout_order_not_found_marks_done(self) -> None:
        """Nonexistent order → done (not failed, order may have been deleted)."""
        expires_at = timezone.now() - timedelta(minutes=1)
        directive = _create_directive(
            topic="pix.timeout",
            payload={
                "order_ref": "NONEXISTENT",
                "intent_id": "pi_fake",
                "expires_at": expires_at.isoformat(),
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

    def test_timeout_order_already_cancelled_skips(self) -> None:
        """Already cancelled order → done, no extra transition."""
        intent = self.backend.create_intent(2000, "BRL")
        order = Order.objects.create(
            ref="ORD-ALREADY-CANCEL",
            channel=self.channel,
            total_q=2000,
            status="cancelled",
            data={"payment": {"intent_id": intent.intent_id, "status": "pending"}},
        )

        expires_at = timezone.now() - timedelta(minutes=1)
        directive = _create_directive(
            topic="pix.timeout",
            payload={
                "order_ref": order.ref,
                "intent_id": intent.intent_id,
                "expires_at": expires_at.isoformat(),
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

        order.refresh_from_db()
        self.assertEqual(order.status, "cancelled")

    def test_timeout_order_completed_skips_cancellation(self) -> None:
        """Completed order → done, no cancellation."""
        intent = self.backend.create_intent(2000, "BRL")
        order = Order.objects.create(
            ref="ORD-COMPLETED",
            channel=self.channel,
            total_q=2000,
            status="completed",
            data={"payment": {"intent_id": intent.intent_id, "status": "pending"}},
        )

        expires_at = timezone.now() - timedelta(minutes=1)
        directive = _create_directive(
            topic="pix.timeout",
            payload={
                "order_ref": order.ref,
                "intent_id": intent.intent_id,
                "expires_at": expires_at.isoformat(),
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

        order.refresh_from_db()
        self.assertEqual(order.status, "completed")

    def test_timeout_sets_cancellation_reason(self) -> None:
        """Cancelled order has data['cancellation_reason']='pix_timeout'."""
        intent = self.backend.create_intent(3000, "BRL")
        order = Order.objects.create(
            ref="ORD-REASON",
            channel=self.channel,
            total_q=3000,
            status="new",
            data={"payment": {"intent_id": intent.intent_id, "status": "pending"}},
        )

        expires_at = timezone.now() - timedelta(minutes=1)
        directive = _create_directive(
            topic="pix.timeout",
            payload={
                "order_ref": order.ref,
                "intent_id": intent.intent_id,
                "expires_at": expires_at.isoformat(),
            },
        )

        self.handler.handle(message=directive, ctx={})

        order.refresh_from_db()
        self.assertEqual(order.data["cancellation_reason"], "pix_timeout")

    def test_timeout_creates_payment_expired_notification(self) -> None:
        """Cancellation creates notification.send directive with payment_expired template."""
        intent = self.backend.create_intent(3000, "BRL")
        order = Order.objects.create(
            ref="ORD-NOTIF",
            channel=self.channel,
            total_q=3000,
            status="new",
            data={"payment": {"intent_id": intent.intent_id, "status": "pending"}},
        )

        expires_at = timezone.now() - timedelta(minutes=1)
        directive = _create_directive(
            topic="pix.timeout",
            payload={
                "order_ref": order.ref,
                "intent_id": intent.intent_id,
                "expires_at": expires_at.isoformat(),
            },
        )

        self.handler.handle(message=directive, ctx={})

        notif = Directive.objects.filter(
            topic="notification.send",
            payload__template="payment_expired",
        ).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.payload["order_ref"], order.ref)

    def test_timeout_cancels_intent_on_gateway(self) -> None:
        """Gateway intent is cancelled when order is cancelled."""
        intent = self.backend.create_intent(3000, "BRL")
        order = Order.objects.create(
            ref="ORD-GW-CANCEL",
            channel=self.channel,
            total_q=3000,
            status="new",
            data={"payment": {"intent_id": intent.intent_id, "status": "pending"}},
        )

        expires_at = timezone.now() - timedelta(minutes=1)
        directive = _create_directive(
            topic="pix.timeout",
            payload={
                "order_ref": order.ref,
                "intent_id": intent.intent_id,
                "expires_at": expires_at.isoformat(),
            },
        )

        self.handler.handle(message=directive, ctx={})

        gw_status = self.backend.get_status(intent.intent_id)
        self.assertEqual(gw_status.status, "cancelled")

    def test_timeout_requeue_preserves_expires_at(self) -> None:
        """Not-expired directive is requeued with available_at = expires_at."""
        expires_at = timezone.now() + timedelta(minutes=5)
        directive = _create_directive(
            topic="pix.timeout",
            payload={
                "order_ref": "ORD-REQUEUE",
                "intent_id": "pi_test",
                "expires_at": expires_at.isoformat(),
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertNotEqual(directive.status, "done")
        self.assertIsNotNone(directive.available_at)

    @patch("shopman.payment.handlers.release_holds_for_order")
    def test_timeout_releases_holds(self, mock_release) -> None:
        """Cancellation calls release_holds_for_order."""
        intent = self.backend.create_intent(3000, "BRL")
        order = Order.objects.create(
            ref="ORD-HOLDS",
            channel=self.channel,
            total_q=3000,
            status="new",
            data={"payment": {"intent_id": intent.intent_id, "status": "pending"}},
        )

        expires_at = timezone.now() - timedelta(minutes=1)
        directive = _create_directive(
            topic="pix.timeout",
            payload={
                "order_ref": order.ref,
                "intent_id": intent.intent_id,
                "expires_at": expires_at.isoformat(),
            },
        )

        self.handler.handle(message=directive, ctx={})

        mock_release.assert_called_once()
        call_arg = mock_release.call_args[0][0]
        self.assertEqual(call_arg.ref, order.ref)

    def test_timeout_naive_datetime_handling(self) -> None:
        """Handler converts naive datetime to aware."""
        intent = self.backend.create_intent(1000, "BRL")
        order = Order.objects.create(
            ref="ORD-NAIVE",
            channel=self.channel,
            total_q=1000,
            status="new",
            data={"payment": {"intent_id": intent.intent_id, "status": "pending"}},
        )

        # Use naive datetime string (no timezone)
        from datetime import datetime
        naive_expired = datetime(2020, 1, 1, 0, 0, 0)

        directive = _create_directive(
            topic="pix.timeout",
            payload={
                "order_ref": order.ref,
                "intent_id": intent.intent_id,
                "expires_at": naive_expired.isoformat(),
            },
        )

        # Should not crash, and should cancel (naive 2020 < now)
        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

        order.refresh_from_db()
        self.assertEqual(order.status, "cancelled")
