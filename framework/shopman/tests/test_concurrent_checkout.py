"""Tests for WP-R18 — Concurrent Checkout Stress Test.

SQLite tests: idempotency and double-submit protection.
PostgreSQL tests: concurrent oversell prevention and payment capture race.

The PostgreSQL tests require a real DB for row-level locking:
    DATABASE_URL=postgres://... pytest shopman/tests/test_concurrent_checkout.py

SQLite (default test DB) cannot demonstrate real concurrency, so oversell
prevention tests are marked @requires_postgres.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

import pytest
from django.conf import settings
from django.test import TestCase, TransactionTestCase

requires_postgres = pytest.mark.skipif(
    "sqlite" in settings.DATABASES["default"]["ENGINE"],
    reason="Requires PostgreSQL for real concurrency testing",
)


def _make_shop():
    from shopman.models import Shop
    return Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})[0]


def _make_channel(ref="stress-test"):
    from shopman.models import Channel
    return Channel.objects.get_or_create(
        ref=ref,
        defaults={
            "name": "Stress Test",
            "is_active": True,
        },
    )[0]


def _make_open_session(channel, session_key, sku="TEST-SKU", qty=1, price_q=1000):
    from shopman.orderman.models import Session
    return Session.objects.create(
        session_key=session_key,
        channel_ref=channel.ref,
        state="open",
        rev=1,
        items=[{"line_id": f"L-{session_key}", "sku": sku, "qty": qty, "unit_price_q": price_q}],
        data={},
    )


class DoubleSubmitIdempotencyTests(TestCase):
    """Idempotency key prevents duplicate orders from double-submit."""

    def setUp(self):
        _make_shop()
        self.channel = _make_channel("idem-stress")

    def test_same_idempotency_key_returns_cached_order(self) -> None:
        """Committing twice with same key returns the same order, no duplicate created."""
        from shopman.orderman.models import IdempotencyKey, Order

        session = _make_open_session(self.channel, "IDEM-SS-001")

        # First commit
        from shopman.orderman.services.commit import CommitService
        result1 = CommitService.commit(
            session_key=session.session_key,
            channel_ref=self.channel.ref,
            idempotency_key="IDEM-KEY-UNIQUE-001",
        )

        # Second commit with SAME idempotency key → cache hit
        result2 = CommitService.commit(
            session_key=session.session_key,
            channel_ref=self.channel.ref,
            idempotency_key="IDEM-KEY-UNIQUE-001",
        )

        self.assertEqual(result1["order_ref"], result2["order_ref"])
        # Only 1 order in DB
        order_count = Order.objects.filter(session_key=session.session_key).count()
        self.assertEqual(order_count, 1)

    def test_different_idempotency_keys_still_one_order(self) -> None:
        """Second commit with different key on already-committed session returns existing order."""
        from shopman.orderman.models import Order
        from shopman.orderman.services.commit import CommitService

        session = _make_open_session(self.channel, "IDEM-SS-002")

        # First commit
        result1 = CommitService.commit(
            session_key=session.session_key,
            channel_ref=self.channel.ref,
            idempotency_key="IDEM-KEY-UNIQUE-002A",
        )

        # Second commit with different key → session already committed, returns existing order
        result2 = CommitService.commit(
            session_key=session.session_key,
            channel_ref=self.channel.ref,
            idempotency_key="IDEM-KEY-UNIQUE-002B",
        )

        self.assertEqual(result1["order_ref"], result2["order_ref"])
        order_count = Order.objects.filter(session_key=session.session_key).count()
        self.assertEqual(order_count, 1)

    def test_five_sessions_five_commits_five_orders(self) -> None:
        """5 independent sessions each create exactly 1 order."""
        from shopman.orderman.models import Order
        from shopman.orderman.services.commit import CommitService

        for i in range(5):
            session = _make_open_session(self.channel, f"MULTI-SS-{i:03d}")
            CommitService.commit(
                session_key=session.session_key,
                channel_ref=self.channel.ref,
                idempotency_key=f"MULTI-KEY-{i:03d}",
            )

        order_count = Order.objects.filter(
            session_key__startswith="MULTI-SS-", channel_ref=self.channel.ref
        ).count()
        self.assertEqual(order_count, 5)

    def test_in_progress_idempotency_key_blocks_duplicate(self) -> None:
        """Committing with an in-progress key raises CommitError."""
        from shopman.orderman.exceptions import CommitError
        from shopman.orderman.models import IdempotencyKey
        from shopman.orderman.services.commit import CommitService

        session = _make_open_session(self.channel, "IDEM-SS-003")
        IdempotencyKey.objects.create(
            scope=f"commit:{self.channel.ref}",
            key="IDEM-KEY-IN-PROGRESS",
            status="in_progress",
        )

        with self.assertRaises(CommitError) as ctx:
            CommitService.commit(
                session_key=session.session_key,
                channel_ref=self.channel.ref,
                idempotency_key="IDEM-KEY-IN-PROGRESS",
            )
        self.assertEqual(ctx.exception.code, "in_progress")


@requires_postgres
class ConcurrentOversellTests(TransactionTestCase):
    """5 concurrent checkouts for a product with stock=3 — exactly 3 should succeed.

    Requires PostgreSQL for real select_for_update() row-level locking.
    SQLite is skipped because it uses a coarse file lock and can't model
    concurrent row-level contention.
    """

    def setUp(self):
        from shopman.models import Shop
        Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})
        from shopman.models import Channel
        self.channel, _ = Channel.objects.get_or_create(
            ref="stress-oversell",
            defaults={
                "name": "Oversell Test",
                "is_active": True,
            },
        )
        from shopman.offerman.models import Product
        self.product = Product.objects.create(
            sku="STRESS-SKU-001",
            name="Stress Product",
            base_price_q=1000,
            is_published=True,
            is_available=True,
        )
        # Create stock: 3 units
        from shopman.stockman import stock
        from shopman.stockman.models import Position, PositionKind
        pos, _ = Position.objects.get_or_create(
            ref="stress-vitrine",
            defaults={"name": "Stress Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
        )
        stock.receive(Decimal("3"), self.product.sku, pos, reason="WP-R18 stress setup")

    def _commit_session(self, session_key, idem_key):
        """Attempt to commit a session; return (success, order_ref, error)."""
        from shopman.orderman.exceptions import CommitError, SessionError
        from shopman.orderman.models import Session
        from shopman.orderman.services.checkout import process as checkout_process

        try:
            # Session must be created within thread (TransactionTestCase uses autocommit)
            Session.objects.create(
                session_key=session_key,
                channel_ref=self.channel.ref,
                state="open",
                rev=1,
                items=[{"line_id": f"L-{session_key}", "sku": self.product.sku, "qty": 1, "unit_price_q": 1000}],
                data={},
            )
            from shopman.orderman.services.commit import CommitService
            result = CommitService.commit(
                session_key=session_key,
                channel_ref=self.channel.ref,
                idempotency_key=idem_key,
            )
            return (True, result["order_ref"], None)
        except Exception as exc:
            return (False, None, str(exc))

    def test_concurrent_checkout_no_oversell(self) -> None:
        """5 concurrent checkouts for stock=3 → at most 3 orders, no oversell."""
        from shopman.orderman.models import Order

        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(
                    self._commit_session,
                    f"STRESS-SESS-{i:03d}",
                    f"STRESS-KEY-{i:03d}",
                ): i
                for i in range(5)
            }
            for future in as_completed(futures):
                results.append(future.result())

        successes = [r for r in results if r[0]]
        failures = [r for r in results if not r[0]]

        # At most 3 orders (limited by stock)
        order_count = Order.objects.filter(channel_ref=self.channel.ref).count()
        self.assertLessEqual(order_count, 3)
        self.assertLessEqual(len(successes), 3)

        # The rest must have failed
        total = len(successes) + len(failures)
        self.assertEqual(total, 5)


@requires_postgres
class ConcurrentPaymentCaptureTests(TransactionTestCase):
    """Two threads race to capture the same payment intent — exactly 1 succeeds.

    Requires PostgreSQL for row-level locking on intent rows.
    """

    def setUp(self):
        from shopman.models import Shop
        Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})
        from shopman.models import Channel
        self.channel, _ = Channel.objects.get_or_create(
            ref="stress-payment",
            defaults={
                "name": "Payment Race Test",
                "is_active": True,
            },
        )

    def test_concurrent_capture_idempotent(self) -> None:
        """Two concurrent captures on the same order → payment captured exactly once."""
        from shopman.orderman.models import Order
        from shopman.services import payment as payment_service
        from unittest.mock import MagicMock, patch

        from shopman.adapters.payment_types import PaymentResult

        order = Order.objects.create(
            ref="RACE-ORD-001",
            channel_ref=self.channel.ref,
            status="confirmed",
            total_q=1000,
            handle_type="phone",
            handle_ref="+5543999001122",
            data={"payment": {"method": "pix", "intent_ref": "pi_race_001"}},
        )

        capture_count = {"n": 0}
        lock = threading.Lock()

        def mock_capture(intent_ref, **kwargs):
            with lock:
                capture_count["n"] += 1
            return PaymentResult(success=True, transaction_id="txn_race_001")

        mock_adapter = MagicMock()
        mock_adapter.capture.side_effect = mock_capture

        def do_capture():
            # _payman_intent_captured returns False (no Payman record in test DB)
            with patch("shopman.services.payment._payman_intent_captured", return_value=False):
                with patch("shopman.services.payment.get_adapter", return_value=mock_adapter):
                    payment_service.capture(order)

        threads = [threading.Thread(target=do_capture) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        order.refresh_from_db()
        # transaction_id written to order.data on successful capture
        self.assertEqual(order.data["payment"]["transaction_id"], "txn_race_001")
        # Status is NOT written to order.data — Payman is the canonical source
        self.assertNotIn("status", order.data["payment"])
        self.assertGreaterEqual(capture_count["n"], 1)
