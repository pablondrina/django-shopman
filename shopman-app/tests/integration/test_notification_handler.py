"""Integration tests for WP-8: notification handler + pluggable backends.

Tests cover:
- NotificationHandler processes directives and dispatches via backend
- NotificationHandler is idempotent on retry (skips already-delivered)
- NotificationHandler uses LogNotificationBackend by default
- Custom backend is called with correct arguments
- register_extensions registers the notification handler in the ordering registry
"""

from unittest.mock import MagicMock

import pytest
from django.test import TestCase

from shopman.contrib.notification_backends import LogNotificationBackend, NotificationBackend
from shopman.contrib.notification_handler import NotificationHandler
from shopman.ordering import registry
from shopman.ordering.models import Channel, Directive


# ---------------------------------------------------------------------------
# NotificationHandler
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestNotificationHandler(TestCase):

    def setUp(self):
        registry.clear()
        self.backend = MagicMock(spec=NotificationBackend)
        self.backend.send.return_value = "delivery:1"
        self.handler = NotificationHandler(backend=self.backend)
        self.channel = Channel.objects.create(ref="pos", name="PDV")

    def tearDown(self):
        registry.clear()

    def test_handler_has_correct_topic(self):
        assert self.handler.topic == "notification.send"

    def test_handler_dispatches_notification(self):
        directive = Directive.objects.create(
            topic="notification.send",
            payload={
                "order_ref": "ORD-1",
                "channel_ref": "pos",
                "session_key": "S-1",
                "template": "order_confirmed",
                "context": {"customer": "Alice"},
            },
        )

        self.handler.handle(message=directive, ctx={})

        self.backend.send.assert_called_once_with(
            order_ref="ORD-1",
            channel_ref="pos",
            template="order_confirmed",
            context={"customer": "Alice", "session_key": "S-1"},
        )

        directive.refresh_from_db()
        assert directive.payload["result"]["delivery_id"] == "delivery:1"

    def test_handler_is_idempotent(self):
        """On retry, skips if delivery_id already recorded."""
        directive = Directive.objects.create(
            topic="notification.send",
            payload={
                "order_ref": "ORD-1",
                "channel_ref": "pos",
                "session_key": "S-1",
                "template": "order_confirmed",
                "result": {"delivery_id": "delivery:already"},
            },
        )

        self.handler.handle(message=directive, ctx={})

        self.backend.send.assert_not_called()

    def test_handler_defaults_template_to_default(self):
        directive = Directive.objects.create(
            topic="notification.send",
            payload={
                "order_ref": "ORD-2",
                "channel_ref": "remote",
                "session_key": "S-2",
            },
        )

        self.handler.handle(message=directive, ctx={})

        self.backend.send.assert_called_once()
        _, kwargs = self.backend.send.call_args
        assert kwargs["template"] == "default"

    def test_handler_persists_result_to_directive(self):
        directive = Directive.objects.create(
            topic="notification.send",
            payload={
                "order_ref": "ORD-3",
                "channel_ref": "pos",
                "session_key": "S-3",
                "template": "order_confirmed",
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        assert "result" in directive.payload
        assert directive.payload["result"]["delivery_id"] == "delivery:1"


# ---------------------------------------------------------------------------
# LogNotificationBackend
# ---------------------------------------------------------------------------


class TestLogNotificationBackend(TestCase):

    def test_send_returns_log_delivery_id(self):
        backend = LogNotificationBackend()
        delivery_id = backend.send(
            order_ref="ORD-1",
            channel_ref="pos",
            template="order_confirmed",
            context={"customer": "Alice"},
        )
        assert delivery_id == "log:ORD-1:order_confirmed"

    def test_backend_satisfies_protocol(self):
        backend = LogNotificationBackend()
        assert isinstance(backend, NotificationBackend)


# ---------------------------------------------------------------------------
# Default backend wiring
# ---------------------------------------------------------------------------


class TestNotificationHandlerDefaults(TestCase):

    def test_default_backend_is_log(self):
        handler = NotificationHandler()
        assert isinstance(handler.backend, LogNotificationBackend)


# ---------------------------------------------------------------------------
# Registration in orchestration
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestNotificationRegistration(TestCase):

    def setUp(self):
        registry.clear()
        import shopman.orchestration as orch
        orch._extensions_registered = False

    def tearDown(self):
        registry.clear()
        import shopman.orchestration as orch
        orch._extensions_registered = False

    def test_register_extensions_adds_notification_handler(self):
        from shopman.orchestration import register_extensions
        register_extensions()
        handler = registry.get_directive_handler("notification.send")
        assert handler is not None
        assert handler.topic == "notification.send"

    def test_register_extensions_still_registers_stock(self):
        from shopman.orchestration import register_extensions
        register_extensions()
        handler = registry.get_directive_handler("stock.hold")
        assert handler is not None

    def test_backward_compat_alias(self):
        from shopman.orchestration import register_stock_extensions
        register_stock_extensions()
        assert registry.get_directive_handler("notification.send") is not None
        assert registry.get_directive_handler("stock.hold") is not None

    def test_setup_channels_registers_notification(self):
        from shopman.orchestration import setup_channels
        setup_channels()
        assert registry.get_directive_handler("notification.send") is not None
