"""
Concurrency tests for WorkOrder optimistic concurrency (rev field).

These tests verify that craft.finish() with select_for_update() and the
rev-based optimistic concurrency check correctly serialise concurrent
operations under PostgreSQL.

IMPORTANT: These tests are skipped on SQLite because:
  - SQLite does not support SELECT FOR UPDATE
  - Only PostgreSQL provides real row-level locking semantics

How finish() protects against concurrent modifications:
  1. Acquires row lock via select_for_update()
  2. Refreshes the caller's object in-place to get current DB state
  3. Checks status is not terminal (raises CraftError('TERMINAL_STATUS') if not)
  4. If expected_rev provided, uses UPDATE WHERE rev=N to atomically bump rev
     and raises StaleRevision if the row was already modified

Two concurrent finish() calls on the same WO:
  - First one acquires the lock, transitions to FINISHED, commits
  - Second one acquires the lock after commit, reads status=FINISHED, raises
    CraftError('TERMINAL_STATUS')
"""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest
from django.conf import settings
from django.db import connection
from django.test import TransactionTestCase
from shopman.craftsman import CraftError, StaleRevision, craft
from shopman.craftsman.models import Recipe, WorkOrder

requires_postgres = pytest.mark.skipif(
    "sqlite" in settings.DATABASES["default"]["ENGINE"],
    reason="Requires PostgreSQL for real concurrency testing",
)


def _make_recipe(code: str) -> Recipe:
    return Recipe.objects.create(
        ref=code,
        name=f"Recipe {code}",
        output_sku=code,
        batch_size=Decimal("10"),
    )


@requires_postgres
class TestConcurrentFinishWorkOrder(TransactionTestCase):
    """
    Two threads both try to finish the same WorkOrder.
    Only one should succeed; the other should get CraftError('TERMINAL_STATUS')
    because after the first finish commits, the WO status is 'finished', which
    select_for_update + refresh_from_db reveals to the second thread.
    """

    def test_concurrent_finish_work_order(self):
        recipe = _make_recipe("close-conc-001")
        wo = craft.plan(recipe, Decimal("50"))

        # Both threads will try to finish the same WO simultaneously
        results = []
        barrier = threading.Barrier(2)

        def attempt_finish(thread_id, finished_qty):
            try:
                barrier.wait()
                # Each thread uses the same wo reference but finish() locks
                # and refreshes the row atomically inside the transaction
                craft.finish(wo, finished=finished_qty)
                results.append(("ok", thread_id))
            except CraftError as e:
                results.append(("err", thread_id, e.code))
            finally:
                connection.close()

        t1 = threading.Thread(target=attempt_finish, args=(1, Decimal("48")))
        t2 = threading.Thread(target=attempt_finish, args=(2, Decimal("45")))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        successes = [r for r in results if r[0] == "ok"]
        failures = [r for r in results if r[0] == "err"]

        # Exactly one finish should succeed
        self.assertEqual(len(successes), 1, f"Expected 1 success, got: {results}")
        self.assertEqual(len(failures), 1, f"Expected 1 failure, got: {results}")
        self.assertEqual(failures[0][2], "TERMINAL_STATUS")

        # WO must be FINISHED with a single finished value
        wo.refresh_from_db()
        self.assertEqual(wo.status, WorkOrder.Status.FINISHED)
        self.assertIsNotNone(wo.finished)


@requires_postgres
class TestFinishWithStaleRevRaisesStaleRevision(TransactionTestCase):
    """
    Verify that passing expected_rev that doesn't match raises StaleRevision.

    This is not a true concurrency test (single thread) but validates the
    rev-based protection that concurrent callers would experience when they
    pass an expected_rev from before a concurrent adjustment happened.
    """

    def test_finish_with_stale_rev_raises(self):
        recipe = _make_recipe("close-stale-rev-001")
        wo = craft.plan(recipe, Decimal("100"))

        # Adjust moves rev forward
        craft.adjust(wo, quantity=Decimal("95"))
        wo.refresh_from_db()
        current_rev = wo.rev

        # Simulate a caller that has an old rev (current_rev - 1)
        with self.assertRaises(StaleRevision) as ctx:
            craft.finish(wo, finished=Decimal("90"), expected_rev=current_rev - 1)

        self.assertEqual(ctx.exception.code, "STALE_REVISION")

        # WO must still be PLANNED — the stale finish did not take effect
        wo.refresh_from_db()
        self.assertEqual(wo.status, WorkOrder.Status.PLANNED)
        self.assertIsNone(wo.finished)
