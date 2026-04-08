"""Tests for signal-driven directive dispatch with transaction safety."""
from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from shopman.omniman import registry
from shopman.omniman.models import Directive


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
        """Creating a queued directive triggers processing after commit."""
        with self.captureOnCommitCallbacks(execute=True):
            directive = Directive.objects.create(
                topic="test.success",
                payload={"key": "value"},
            )
        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.assertEqual(self.success_handler.calls, 1)

    def test_directive_not_dispatched_when_status_not_queued(self) -> None:
        """Directives created with non-queued status are not dispatched."""
        with self.captureOnCommitCallbacks(execute=True):
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
        with self.captureOnCommitCallbacks(execute=True):
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
        with self.captureOnCommitCallbacks(execute=True):
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
        from shopman.omniman.dispatch import _process_directive
        _process_directive(directive)

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertEqual(directive.attempts, 5)

    def test_no_handler_leaves_directive_queued(self) -> None:
        """Directive with no registered handler stays queued."""
        with self.captureOnCommitCallbacks(execute=True):
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
        with self.captureOnCommitCallbacks(execute=True):
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
        with self.captureOnCommitCallbacks(execute=True):
            directive = Directive.objects.create(
                topic="test.success",
                payload={},
            )
        initial_calls = self.success_handler.calls

        # Update the directive
        with self.captureOnCommitCallbacks(execute=True):
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

        with self.captureOnCommitCallbacks(execute=True):
            Directive.objects.create(topic="parent", payload={})

        # Child should still be queued (reentrancy guard)
        child = Directive.objects.get(pk=created_ids[0])
        self.assertEqual(child.status, "queued")

    def test_directive_processed_only_after_commit(self) -> None:
        """Directive callback is deferred — not executed inside the transaction."""
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            directive = Directive.objects.create(
                topic="test.success",
                payload={},
            )
            # Before callbacks execute, directive is still queued
            directive.refresh_from_db()
            self.assertEqual(directive.status, "queued")
            self.assertEqual(self.success_handler.calls, 0)

        # Now execute the captured callbacks
        for callback in callbacks:
            callback()

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.assertEqual(self.success_handler.calls, 1)

    def test_refetch_ensures_fresh_state(self) -> None:
        """on_commit callback re-fetches directive, skips if status changed."""
        from shopman.omniman.dispatch import _on_commit_callback

        with self.captureOnCommitCallbacks(execute=True):
            directive = Directive.objects.create(
                topic="test.success",
                payload={},
            )

        # directive is now "done"; reset handler count
        self.success_handler.calls = 0

        # Manually invoke callback again — should skip because status != "queued"
        _on_commit_callback(directive.pk, directive.topic)

        self.assertEqual(self.success_handler.calls, 0)

    def test_refetch_skips_deleted_directive(self) -> None:
        """on_commit callback handles deleted directive gracefully."""
        from shopman.omniman.dispatch import _on_commit_callback

        # Use a non-existent pk
        _on_commit_callback(999999, "test.success")
        # No error raised, handler not called
        self.assertEqual(self.success_handler.calls, 0)

    def test_reentrancy_guard_with_on_commit(self) -> None:
        """Child directives created during on_commit processing stay queued."""
        child_ids = []

        class SpawnerHandler:
            topic = "spawner"

            def handle(self, *, message, ctx):
                child = Directive.objects.create(topic="spawned", payload={})
                child_ids.append(child.pk)
                message.status = "done"
                message.save(update_fields=["status"])

        class SpawnedHandler:
            topic = "spawned"

            def handle(self, *, message, ctx):
                message.status = "done"
                message.save(update_fields=["status"])

        registry.register_directive_handler(SpawnerHandler())
        registry.register_directive_handler(SpawnedHandler())

        with self.captureOnCommitCallbacks(execute=True):
            Directive.objects.create(topic="spawner", payload={})

        # Parent processed, child stays queued (reentrancy guard)
        self.assertTrue(len(child_ids) > 0)
        child = Directive.objects.get(pk=child_ids[0])
        self.assertEqual(child.status, "queued")


class DirectiveRollbackTests(TransactionTestCase):
    """Tests requiring real transaction rollback (TransactionTestCase)."""

    def setUp(self) -> None:
        super().setUp()
        registry.clear()
        self.success_handler = SuccessHandler()
        registry.register_directive_handler(self.success_handler)

    def tearDown(self) -> None:
        registry.clear()
        super().tearDown()

    def test_directive_not_processed_on_rollback(self) -> None:
        """on_commit callbacks do not fire when the transaction is rolled back."""
        try:
            with transaction.atomic():
                Directive.objects.create(
                    topic="test.success",
                    payload={"should": "rollback"},
                )
                raise Exception("force rollback")
        except Exception:
            pass

        # Directive was rolled back — nothing in DB
        self.assertEqual(Directive.objects.count(), 0)
        # Handler was never called
        self.assertEqual(self.success_handler.calls, 0)
