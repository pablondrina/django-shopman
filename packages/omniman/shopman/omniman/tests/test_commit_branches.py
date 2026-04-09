"""
Tests for additional branches in CommitService.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from shopman.omniman.exceptions import CommitError, SessionError
from shopman.omniman.models import Channel, IdempotencyKey, Order, Session
from shopman.omniman.services import CommitService


class CommitIdempotencyTests(TestCase):
    """Tests for idempotency handling in CommitService."""

    def setUp(self) -> None:
        self.channel = Channel.objects.create(
            ref="commit-idem-test",
            name="Commit Idempotency Test",
        )
        self.session = Session.objects.create(
            session_key="IDEM-SESS-001",
            channel=self.channel,
            state="open",
            rev=1,
            items=[{"line_id": "L1", "sku": "A", "qty": 1, "unit_price_q": 1000}],
        )

    def test_commit_in_progress_raises_error(self) -> None:
        """Should raise CommitError when commit is already in progress."""
        # Create an in-progress idempotency key with correct scope
        IdempotencyKey.objects.create(
            scope=f"commit:{self.channel.ref}",
            key="in-progress-key",
            status="in_progress",
        )

        with self.assertRaises(CommitError) as ctx:
            CommitService.commit(
                session_key=self.session.session_key,
                channel_ref=self.channel.ref,
                idempotency_key="in-progress-key",
            )

        self.assertEqual(ctx.exception.code, "in_progress")

    def test_commit_returns_cached_response(self) -> None:
        """Should return cached response for completed idempotency key."""
        cached_response = {"order_ref": "ORD-CACHED-001", "status": "success"}
        IdempotencyKey.objects.create(
            scope=f"commit:{self.channel.ref}",
            key="done-key",
            status="done",
            response_body=cached_response,
        )

        result = CommitService.commit(
            session_key=self.session.session_key,
            channel_ref=self.channel.ref,
            idempotency_key="done-key",
        )

        self.assertEqual(result, cached_response)


class CommitSessionNotFoundTests(TestCase):
    """Tests for session not found in CommitService."""

    def setUp(self) -> None:
        self.channel = Channel.objects.create(
            ref="commit-notfound-test",
            name="Not Found Test",
        )

    def test_commit_raises_session_not_found(self) -> None:
        """Should raise SessionError when session doesn't exist."""
        with self.assertRaises(SessionError) as ctx:
            CommitService.commit(
                session_key="NONEXISTENT",
                channel_ref=self.channel.ref,
                idempotency_key="key-001",
            )

        self.assertEqual(ctx.exception.code, "not_found")


class CommitAbandonedSessionTests(TestCase):
    """Tests for abandoned session handling."""

    def setUp(self) -> None:
        self.channel = Channel.objects.create(
            ref="commit-abandoned-test",
            name="Abandoned Test",
        )
        self.session = Session.objects.create(
            session_key="ABANDONED-SESS-001",
            channel=self.channel,
            state="abandoned",
            rev=1,
            items=[],
        )

    def test_commit_raises_for_abandoned_session(self) -> None:
        """Should raise CommitError for abandoned session."""
        with self.assertRaises(CommitError) as ctx:
            CommitService.commit(
                session_key=self.session.session_key,
                channel_ref=self.channel.ref,
                idempotency_key="key-abandoned",
            )

        self.assertEqual(ctx.exception.code, "abandoned")


class CommitAlreadyCommittedTests(TestCase):
    """Tests for already committed session handling."""

    def setUp(self) -> None:
        self.channel = Channel.objects.create(
            ref="commit-already-test",
            name="Already Committed Test",
        )
        self.session = Session.objects.create(
            session_key="ALREADY-SESS-001",
            channel=self.channel,
            state="committed",
            rev=1,
            items=[{"line_id": "L1", "sku": "A", "qty": 1, "unit_price_q": 1000}],
        )
        # Create corresponding order
        self.order = Order.objects.create(
            ref="ORD-ALREADY-001",
            channel=self.channel,
            session_key=self.session.session_key,
            status="new",
            total_q=1000,
        )

    def test_commit_returns_existing_order_for_already_committed(self) -> None:
        """Should return existing order for already committed session."""
        result = CommitService.commit(
            session_key=self.session.session_key,
            channel_ref=self.channel.ref,
            idempotency_key="key-already",
        )

        self.assertEqual(result["order_ref"], "ORD-ALREADY-001")
        self.assertEqual(result["status"], "already_committed")

    def test_commit_raises_when_committed_but_no_order(self) -> None:
        """Should raise CommitError when session committed but order missing."""
        self.order.delete()  # Remove the order

        with self.assertRaises(CommitError) as ctx:
            CommitService.commit(
                session_key=self.session.session_key,
                channel_ref=self.channel.ref,
                idempotency_key="key-no-order",
            )

        self.assertEqual(ctx.exception.code, "already_committed")


class CommitHoldExpiryTests(TestCase):
    """Tests for hold expiry checking in CommitService."""

    def setUp(self) -> None:
        self.channel = Channel.objects.create(
            ref="commit-expiry-test",
            name="Hold Expiry Test",
        )

    def test_commit_raises_for_expired_hold_in_result(self) -> None:
        """Should raise CommitError when hold in result is expired."""
        expired_time = (timezone.now() - timedelta(minutes=5)).isoformat()

        session = Session.objects.create(
            session_key="EXPIRY-SESS-001",
            channel=self.channel,
            state="open",
            rev=1,
            items=[{"line_id": "L1", "sku": "A", "qty": 1, "unit_price_q": 1000}],
            data={
                "checks": {
                    "stock": {
                        "rev": 1,
                        "result": {
                            "holds": [
                                {"hold_id": "H1", "expires_at": expired_time}
                            ]
                        }
                    }
                },
                "issues": [],
            },
        )

        with self.assertRaises(CommitError) as ctx:
            CommitService.commit(
                session_key=session.session_key,
                channel_ref=self.channel.ref,
                idempotency_key="key-expired-hold",
                channel_config={"rules": {"checks": ["stock"]}},
            )

        self.assertEqual(ctx.exception.code, "hold_expired")

    def test_commit_allows_hold_without_expires_at(self) -> None:
        """Should allow holds without expires_at field."""
        session = Session.objects.create(
            session_key="NOEXPIRY-SESS-001",
            channel=self.channel,
            state="open",
            rev=1,
            items=[{"line_id": "L1", "sku": "A", "qty": 1, "unit_price_q": 1000}],
            data={
                "checks": {
                    "stock": {
                        "rev": 1,
                        "result": {
                            "holds": [
                                {"hold_id": "H1"}  # No expires_at
                            ]
                        }
                    }
                },
                "issues": [],
            },
        )

        # Should succeed (no expiry = eternal hold)
        result = CommitService.commit(
            session_key=session.session_key,
            channel_ref=self.channel.ref,
            idempotency_key="key-no-expiry",
            channel_config={"rules": {"checks": ["stock"]}},
        )

        self.assertIn("order_ref", result)

    def test_commit_raises_for_expired_hold_expires_at_in_result(self) -> None:
        """Should raise CommitError when hold_expires_at in result is expired."""
        expired_time = (timezone.now() - timedelta(minutes=5)).isoformat()

        session = Session.objects.create(
            session_key="EXPIRY-RESULT-001",
            channel=self.channel,
            state="open",
            rev=1,
            items=[{"line_id": "L1", "sku": "A", "qty": 1, "unit_price_q": 1000}],
            data={
                "checks": {
                    "stock": {
                        "rev": 1,
                        "result": {
                            "hold_expires_at": expired_time,
                        }
                    }
                },
                "issues": [],
            },
        )

        with self.assertRaises(CommitError) as ctx:
            CommitService.commit(
                session_key=session.session_key,
                channel_ref=self.channel.ref,
                idempotency_key="key-expired-result",
                channel_config={"rules": {"checks": ["stock"]}},
            )

        self.assertEqual(ctx.exception.code, "hold_expired")
