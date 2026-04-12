"""
Concurrency tests for Stockman hold lifecycle.

These tests verify that the select_for_update() locking in
StockHolds actually serialises concurrent operations under PostgreSQL.

IMPORTANT: These tests are skipped on SQLite because:
  - SQLite does not support SELECT FOR UPDATE
  - SQLite uses a coarse file-level lock, not row-level locks
  - Only PostgreSQL (and compatible DBs) provide real concurrent isolation

Run with PostgreSQL:
    DATABASE_URL=postgres://... pytest shopman/stocking/tests/test_concurrency.py
"""

from __future__ import annotations

import threading
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.db import connection
from django.test import TransactionTestCase

from shopman.stockman import stock, StockError
from shopman.stockman.models import Position, PositionKind, Hold, HoldStatus


requires_postgres = pytest.mark.skipif(
    "sqlite" in settings.DATABASES["default"]["ENGINE"],
    reason="Requires PostgreSQL for real concurrency testing",
)


def _make_position(ref: str) -> Position:
    pos, _ = Position.objects.get_or_create(
        ref=ref,
        defaults={
            "name": ref,
            "kind": PositionKind.PHYSICAL,
            "is_saleable": True,
        },
    )
    return pos


@requires_postgres
class TestConcurrentHoldSameSku(TransactionTestCase):
    """
    Two threads attempt to hold the same SKU where total qty > available.
    Only one should succeed; the other should raise StockError.

    This exercises select_for_update() inside StockHolds.hold() which
    acquires a row lock on the Quant before checking available quantity.
    """

    def test_concurrent_hold_same_sku(self):
        today = date.today()
        product = SimpleNamespace(sku="HOLD-CONC-001")
        vitrine = _make_position("vitrine-conc-1")

        # Stock = 5 units, each thread tries to hold 4 (total 8 > 5)
        stock.receive(Decimal("5"), product.sku, vitrine, reason="Setup")

        results = []
        barrier = threading.Barrier(2)

        def attempt_hold(thread_id):
            try:
                barrier.wait()  # Both threads start at the same time
                hold_id = stock.hold(Decimal("4"), product, today)
                results.append(("ok", thread_id, hold_id))
            except StockError as e:
                results.append(("err", thread_id, str(e)))
            finally:
                connection.close()

        t1 = threading.Thread(target=attempt_hold, args=(1,))
        t2 = threading.Thread(target=attempt_hold, args=(2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        successes = [r for r in results if r[0] == "ok"]
        failures = [r for r in results if r[0] == "err"]

        # Exactly one thread should succeed
        self.assertEqual(len(successes), 1, f"Expected 1 success, got: {results}")
        self.assertEqual(len(failures), 1, f"Expected 1 failure, got: {results}")

        # The successful hold should exist in DB
        hold_id = successes[0][2]
        pk = int(hold_id.split(":")[1])
        hold = Hold.objects.get(pk=pk)
        self.assertEqual(hold.status, HoldStatus.PENDING)
        self.assertEqual(hold.quantity, Decimal("4"))


@requires_postgres
class TestConcurrentFulfillSameHold(TransactionTestCase):
    """
    Two threads attempt to fulfill the same hold_id.
    Only one should succeed (idempotency via select_for_update status check).

    The fulfill() method requires status == CONFIRMED. After the first
    thread transitions to FULFILLED, the second thread reads the locked
    row and raises StockError('INVALID_STATUS').
    """

    def test_concurrent_fulfill_same_hold(self):
        today = date.today()
        product = SimpleNamespace(sku="HOLD-CONC-002")
        vitrine = _make_position("vitrine-conc-2")

        stock.receive(Decimal("10"), product.sku, vitrine, reason="Setup")
        hold_id = stock.hold(Decimal("3"), product, today)
        stock.confirm(hold_id)

        results = []
        barrier = threading.Barrier(2)

        def attempt_fulfill(thread_id):
            try:
                barrier.wait()
                move = stock.fulfill(hold_id)
                results.append(("ok", thread_id, move.pk))
            except StockError as e:
                results.append(("err", thread_id, str(e)))
            finally:
                connection.close()

        t1 = threading.Thread(target=attempt_fulfill, args=(1,))
        t2 = threading.Thread(target=attempt_fulfill, args=(2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        successes = [r for r in results if r[0] == "ok"]
        failures = [r for r in results if r[0] == "err"]

        # Exactly one fulfill should succeed
        self.assertEqual(len(successes), 1, f"Expected 1 success, got: {results}")
        self.assertEqual(len(failures), 1, f"Expected 1 failure, got: {results}")

        # Hold must be FULFILLED, not in any other state
        pk = int(hold_id.split(":")[1])
        hold = Hold.objects.get(pk=pk)
        self.assertEqual(hold.status, HoldStatus.FULFILLED)


@requires_postgres
class TestConcurrentReleaseAndFulfill(TransactionTestCase):
    """
    One thread releases while another fulfills the same hold.
    Result must be consistent — either RELEASED or FULFILLED, never both
    and never in a partially-written intermediate state.

    Both operations use select_for_update() so one acquires the lock and
    completes while the other reads the resulting terminal status and
    raises StockError('INVALID_STATUS').
    """

    def test_concurrent_release_and_fulfill(self):
        today = date.today()
        product = SimpleNamespace(sku="HOLD-CONC-003")
        vitrine = _make_position("vitrine-conc-3")

        stock.receive(Decimal("10"), product.sku, vitrine, reason="Setup")
        hold_id = stock.hold(Decimal("5"), product, today)
        stock.confirm(hold_id)

        results = []
        barrier = threading.Barrier(2)

        def attempt_release(thread_id):
            try:
                barrier.wait()
                stock.release(hold_id, reason="Cancelamento")
                results.append(("release_ok", thread_id))
            except StockError as e:
                results.append(("release_err", thread_id, str(e)))
            finally:
                connection.close()

        def attempt_fulfill(thread_id):
            try:
                barrier.wait()
                stock.fulfill(hold_id)
                results.append(("fulfill_ok", thread_id))
            except StockError as e:
                results.append(("fulfill_err", thread_id, str(e)))
            finally:
                connection.close()

        t1 = threading.Thread(target=attempt_release, args=(1,))
        t2 = threading.Thread(target=attempt_fulfill, args=(2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly one operation should succeed
        ok_count = sum(1 for r in results if r[0].endswith("_ok"))
        err_count = sum(1 for r in results if r[0].endswith("_err"))
        self.assertEqual(ok_count, 1, f"Expected 1 success, got: {results}")
        self.assertEqual(err_count, 1, f"Expected 1 failure, got: {results}")

        # Hold must be in exactly one terminal state
        pk = int(hold_id.split(":")[1])
        hold = Hold.objects.get(pk=pk)
        self.assertIn(
            hold.status,
            [HoldStatus.RELEASED, HoldStatus.FULFILLED],
            f"Unexpected status: {hold.status}",
        )
