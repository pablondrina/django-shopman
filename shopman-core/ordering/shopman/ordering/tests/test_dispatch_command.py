"""Tests for dispatch_directives management command."""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from shopman.ordering import registry
from shopman.ordering.models import Directive


class SuccessHandler:
    topic = "cmd.success"

    def handle(self, *, message, ctx):
        message.status = "done"
        message.save(update_fields=["status"])


@pytest.mark.django_db
class TestDispatchDirectivesCommand(TestCase):
    def test_dispatches_pending_directives(self):
        registry.register_directive_handler(SuccessHandler())

        d = Directive.objects.create(topic="cmd.success", payload={})
        d.status = "queued"
        d.available_at = timezone.now() - timedelta(seconds=1)
        d.save(update_fields=["status", "available_at"])

        out = StringIO()
        call_command("dispatch_directives", stdout=out)
        output = out.getvalue()

        assert "1 directive(s) dispatched." in output
        d.refresh_from_db()
        assert d.status == "done"

    def test_no_pending(self):
        out = StringIO()
        call_command("dispatch_directives", stdout=out)
        assert "0 directive(s) dispatched." in out.getvalue()

    def test_dry_run_lists_without_processing(self):
        d = Directive.objects.create(topic="cmd.success", payload={})
        d.status = "queued"
        d.available_at = timezone.now() - timedelta(seconds=1)
        d.save(update_fields=["status", "available_at"])

        out = StringIO()
        call_command("dispatch_directives", "--dry-run", stdout=out)
        output = out.getvalue()

        assert "dry-run" in output
        assert "1 pending directive(s)" in output
        assert "cmd.success" in output

        d.refresh_from_db()
        assert d.status == "queued"

    def test_dry_run_no_pending(self):
        out = StringIO()
        call_command("dispatch_directives", "--dry-run", stdout=out)
        assert "0 pending directive(s)" in out.getvalue()

    @patch("shopman.ordering.management.commands.dispatch_directives.dispatch_pending_directives")
    def test_calls_dispatch_pending_directives(self, mock_dispatch):
        mock_dispatch.return_value = 3
        out = StringIO()
        call_command("dispatch_directives", stdout=out)
        mock_dispatch.assert_called_once()
        assert "3 directive(s) dispatched." in out.getvalue()
