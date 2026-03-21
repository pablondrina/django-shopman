"""Testes do Dispatch do Ordering kernel."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import TestCase
from django.utils import timezone

from shopman.ordering import registry
from shopman.ordering.dispatch import dispatch_pending_directives, MAX_ATTEMPTS
from shopman.ordering.models import Channel, Directive


class SuccessHandler:
    topic = "test.success"

    def handle(self, *, message, ctx):
        message.status = "done"
        message.save(update_fields=["status"])


class FailHandler:
    topic = "test.fail"

    def handle(self, *, message, ctx):
        raise RuntimeError("boom")


@pytest.mark.django_db
class TestDispatch(TestCase):
    def test_directive_auto_dispatched_on_create(self):
        registry.register_directive_handler(SuccessHandler())
        d = Directive.objects.create(topic="test.success", payload={"key": "val"})
        d.refresh_from_db()
        assert d.status == "done"
        assert d.attempts == 1

    def test_directive_no_handler_stays_queued(self):
        d = Directive.objects.create(topic="no.handler", payload={})
        d.refresh_from_db()
        assert d.status == "queued"
        assert d.attempts == 0

    def test_directive_fail_retries(self):
        registry.register_directive_handler(FailHandler())
        d = Directive.objects.create(topic="test.fail", payload={})
        d.refresh_from_db()
        assert d.status == "queued"
        assert d.attempts == 1
        assert "boom" in d.last_error

    def test_reentrancy_guard(self):
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
        assert child.status == "queued"

    def test_directive_fails_after_max_attempts(self):
        """After MAX_ATTEMPTS failures, directive is marked as 'failed'."""
        registry.register_directive_handler(FailHandler())

        # Create directive — first attempt happens automatically via signal
        d = Directive.objects.create(topic="test.fail", payload={})
        d.refresh_from_db()
        assert d.status == "queued"
        assert d.attempts == 1

        # Simulate remaining attempts until MAX_ATTEMPTS
        for attempt in range(2, MAX_ATTEMPTS + 1):
            d.available_at = timezone.now() - timedelta(seconds=1)
            d.save(update_fields=["available_at"])
            dispatch_pending_directives()
            d.refresh_from_db()

        assert d.status == "failed"
        assert d.attempts == MAX_ATTEMPTS
        assert "boom" in d.last_error

    def test_dispatch_pending_directives_sweep(self):
        """dispatch_pending_directives() processes all queued directives."""
        registry.register_directive_handler(SuccessHandler())

        # Create directives with signal dispatch suppressed via reentrancy guard
        now = timezone.now()
        d1 = Directive(topic="test.success", payload={"n": 1}, available_at=now - timedelta(seconds=1))
        d1.save()  # signal fires but handler succeeds, so this one is done

        # Create a directive that won't auto-dispatch (future available_at)
        d2 = Directive.objects.create(topic="test.success", payload={"n": 2})
        d2.status = "queued"
        d2.available_at = now - timedelta(seconds=1)
        d2.save(update_fields=["status", "available_at"])

        count = dispatch_pending_directives()

        d2.refresh_from_db()
        assert d2.status == "done"
        assert count >= 1
