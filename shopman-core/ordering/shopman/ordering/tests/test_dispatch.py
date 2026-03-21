"""Tests for signal-driven directive dispatch."""
from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from shopman.ordering import registry
from shopman.ordering.models import Directive


class SuccessHandler:
    topic = "test.success"

    def __init__(self) -> None:
        self.calls = 0

    def handle(self, *, message: Directive, ctx: dict) -> None:
        self.calls += 1
        message.status = "done"
        message.save(update_fields=["status", "updated_at"])


class FailHandler:
    topic = "test.fail"

    def __init__(self) -> None:
        self.calls = 0

    def handle(self, *, message: Directive, ctx: dict) -> None:
        self.calls += 1
        raise RuntimeError("boom")


class FailOnceHandler:
    """Fails on first call, succeeds on subsequent calls."""
    topic = "test.fail_once"

    def __init__(self) -> None:
        self.calls = 0

    def handle(self, *, message: Directive, ctx: dict) -> None:
        self.calls += 1
        if self.calls <= 1:
            raise RuntimeError("transient failure")
        message.status = "done"
        message.save(update_fields=["status", "updated_at"])


class DirectiveDispatchTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        registry.clear()
        self.success_handler = SuccessHandler()
        self.fail_handler = FailHandler()
        registry.register_directive_handler(self.success_handler)
        registry.register_directive_handler(self.fail_handler)

    def tearDown(self) -> None:
        registry.clear()
        super().tearDown()

    def test_directive_processed_automatically_on_create(self) -> None:
        """Creating a queued directive triggers immediate processing."""
        directive = Directive.objects.create(
            topic="test.success",
            payload={"key": "value"},
        )
        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.assertEqual(self.success_handler.calls, 1)

    def test_directive_not_dispatched_when_status_not_queued(self) -> None:
        """Directives created with non-queued status are not dispatched."""
        directive = Directive.objects.create(
            topic="test.success",
            payload={},
            status="done",
        )
        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.assertEqual(self.success_handler.calls, 0)

    def test_failed_handler_marks_queued_with_backoff(self) -> None:
        """A failing handler sets status=queued with backoff on first attempt."""
        directive = Directive.objects.create(
            topic="test.fail",
            payload={},
        )
        directive.refresh_from_db()
        self.assertEqual(directive.status, "queued")
        self.assertEqual(directive.attempts, 1)
        self.assertIn("boom", directive.last_error)
        self.assertGreater(directive.available_at, timezone.now())

    def test_failed_handler_marks_failed_after_max_attempts(self) -> None:
        """After max attempts, directive is marked as failed."""
        directive = Directive.objects.create(
            topic="test.fail",
            payload={},
        )
        # Simulate having reached max attempts - 1
        directive.refresh_from_db()
        directive.attempts = 4
        directive.status = "queued"
        directive.available_at = timezone.now() - timedelta(seconds=1)
        directive.save(update_fields=["attempts", "status", "available_at", "updated_at"])

        # Now process again via the dispatch function directly
        from shopman.ordering.dispatch import _process_directive
        _process_directive(directive)

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertEqual(directive.attempts, 5)

    def test_no_handler_leaves_directive_queued(self) -> None:
        """Directive with no registered handler stays queued."""
        directive = Directive.objects.create(
            topic="test.unregistered",
            payload={},
        )
        directive.refresh_from_db()
        # Status stays queued (signal fires but no handler)
        self.assertEqual(directive.status, "queued")

    def test_opportunistic_retry_picks_up_failed_directives(self) -> None:
        """After processing a new directive, retries queued ones from same topic."""
        # Use bulk_create to bypass post_save signal (no auto-dispatch)
        old = Directive(
            topic="test.success",
            payload={"id": "old"},
            status="queued",
            attempts=1,
            available_at=timezone.now() - timedelta(seconds=10),
            last_error="previous failure",
        )
        Directive.objects.bulk_create([old])

        # Create a new directive — triggers dispatch + opportunistic retry
        new = Directive.objects.create(
            topic="test.success",
            payload={"id": "new"},
        )

        # New directive: processed immediately
        new.refresh_from_db()
        self.assertEqual(new.status, "done")

        # Old directive: retried opportunistically
        old.refresh_from_db()
        self.assertEqual(old.status, "done")

    def test_update_does_not_trigger_dispatch(self) -> None:
        """Updating an existing directive does not re-trigger dispatch."""
        directive = Directive.objects.create(
            topic="test.success",
            payload={},
        )
        initial_calls = self.success_handler.calls

        # Update the directive
        directive.last_error = "test"
        directive.save(update_fields=["last_error"])

        self.assertEqual(self.success_handler.calls, initial_calls)

    def test_reentrancy_guard(self) -> None:
        """Handler that creates child directives should not cascade."""
        created_ids = []

        class ParentHandler:
            topic = "parent"

            def handle(self, *, message, ctx):
                child = Directive.objects.create(topic="child", payload={})
                created_ids.append(child.pk)
                message.status = "done"
                message.save(update_fields=["status"])

        class ChildHandler:
            topic = "child"

            def handle(self, *, message, ctx):
                message.status = "done"
                message.save(update_fields=["status"])

        registry.register_directive_handler(ParentHandler())
        registry.register_directive_handler(ChildHandler())

        Directive.objects.create(topic="parent", payload={})

        # Child should still be queued (reentrancy guard)
        child = Directive.objects.get(pk=created_ids[0])
        self.assertEqual(child.status, "queued")
