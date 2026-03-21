"""Testes do Dispatch do Ordering kernel."""

import pytest
from django.test import TestCase

from shopman.ordering import registry
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
