"""
Concurrency tests for PaymentIntent status transitions.

These tests verify that transition_status() with select_for_update()
correctly serialises concurrent operations under PostgreSQL.

IMPORTANT: These tests are skipped on SQLite because:
  - SQLite does not support SELECT FOR UPDATE
  - Only PostgreSQL provides real row-level locking semantics

The PaymentIntent.transition_status() method uses:
    PaymentIntent.objects.select_for_update().get(pk=self.pk)

This ensures that the second thread reads the row after the first has
committed, and the TRANSITIONS dict check then raises PaymentError.
"""

from __future__ import annotations

import threading

import pytest
from django.conf import settings
from django.db import connection
from django.test import TransactionTestCase
from shopman.payman.exceptions import PaymentError
from shopman.payman.models import PaymentIntent

requires_postgres = pytest.mark.skipif(
    "sqlite" in settings.DATABASES["default"]["ENGINE"],
    reason="Requires PostgreSQL for real concurrency testing",
)


def _make_pending_intent(ref: str) -> PaymentIntent:
    return PaymentIntent.objects.create(
        ref=ref,
        order_ref="ORD-CONC",
        method="pix",
        amount_q=5000,
    )


@requires_postgres
class TestConcurrentCapture(TransactionTestCase):
    """
    Two threads both try to transition the same intent from AUTHORIZED to CAPTURED.
    Only one should succeed; the second reads the already-CAPTURED status and
    raises PaymentError('invalid_transition') because CAPTURED→CAPTURED is not
    in the TRANSITIONS dict.
    """

    def test_concurrent_capture(self):
        intent = _make_pending_intent("PAY-CONC-CAP-001")
        intent.transition_status(PaymentIntent.Status.AUTHORIZED)

        # Reload fresh instances for each thread to simulate two separate API calls
        results = []
        barrier = threading.Barrier(2)

        def attempt_capture(thread_id):
            try:
                barrier.wait()
                # Each thread loads its own instance to simulate a separate request
                local_intent = PaymentIntent.objects.get(pk=intent.pk)
                local_intent.transition_status(PaymentIntent.Status.CAPTURED)
                results.append(("ok", thread_id))
            except PaymentError as e:
                results.append(("err", thread_id, e.code))
            finally:
                connection.close()

        t1 = threading.Thread(target=attempt_capture, args=(1,))
        t2 = threading.Thread(target=attempt_capture, args=(2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        successes = [r for r in results if r[0] == "ok"]
        failures = [r for r in results if r[0] == "err"]

        # Exactly one capture should succeed
        self.assertEqual(len(successes), 1, f"Expected 1 success, got: {results}")
        self.assertEqual(len(failures), 1, f"Expected 1 failure, got: {results}")
        self.assertEqual(failures[0][2], "invalid_transition")

        # Final status must be CAPTURED
        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentIntent.Status.CAPTURED)


@requires_postgres
class TestConcurrentRefundAndCapture(TransactionTestCase):
    """
    One thread tries to cancel the intent while another tries to capture it.
    Both start from AUTHORIZED. Only one transition can win; the other
    reads the committed status and raises PaymentError for an invalid transition.

    This verifies that the select_for_update() in transition_status() prevents
    both a capture and a cancellation from succeeding simultaneously.
    """

    def test_concurrent_refund_and_capture(self):
        intent = _make_pending_intent("PAY-CONC-RFND-001")
        intent.transition_status(PaymentIntent.Status.AUTHORIZED)

        results = []
        barrier = threading.Barrier(2)

        def attempt_cancel(thread_id):
            try:
                barrier.wait()
                local_intent = PaymentIntent.objects.get(pk=intent.pk)
                local_intent.transition_status(PaymentIntent.Status.CANCELLED)
                results.append(("cancel_ok", thread_id))
            except PaymentError as e:
                results.append(("cancel_err", thread_id, e.code))
            finally:
                connection.close()

        def attempt_capture(thread_id):
            try:
                barrier.wait()
                local_intent = PaymentIntent.objects.get(pk=intent.pk)
                local_intent.transition_status(PaymentIntent.Status.CAPTURED)
                results.append(("capture_ok", thread_id))
            except PaymentError as e:
                results.append(("capture_err", thread_id, e.code))
            finally:
                connection.close()

        t1 = threading.Thread(target=attempt_cancel, args=(1,))
        t2 = threading.Thread(target=attempt_capture, args=(2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly one operation should succeed
        ok_count = sum(1 for r in results if r[0].endswith("_ok"))
        err_count = sum(1 for r in results if r[0].endswith("_err"))
        self.assertEqual(ok_count, 1, f"Expected 1 success, got: {results}")
        self.assertEqual(err_count, 1, f"Expected 1 failure, got: {results}")

        # Final status must be one of the two competed statuses — never AUTHORIZED
        intent.refresh_from_db()
        self.assertIn(
            intent.status,
            [PaymentIntent.Status.CANCELLED, PaymentIntent.Status.CAPTURED],
            f"Unexpected final status: {intent.status}",
        )
