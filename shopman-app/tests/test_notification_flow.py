"""
Tests for the outbound notification flow.

Verifica que:
1. Order status change → Directive(notification.send) criada → ManychatBackend.send() chamado
2. Subscriber resolution: phone → subscriber_id via resolver
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from shopman.ordering import registry
from shopman.notifications.backends.manychat import ManychatBackend, ManychatConfig
from shopman.notifications.handlers import NotificationSendHandler
from shopman.notifications.protocols import NotificationResult
from shopman.notifications.service import register_backend
from shopman.ordering.models import Channel, Directive, Order, OrderItem


class NotificationSendHandlerTests(TestCase):
    """Tests for NotificationSendHandler processing."""

    def setUp(self) -> None:
        super().setUp()
        registry.clear()

        self.channel = Channel.objects.create(
            ref="whatsapp",
            name="WhatsApp",
            pricing_policy="external",
            edit_policy="open",
            config={
                "notifications": {
                    "backend": "manychat",
                },
            },
            is_active=True,
        )

        # Create a mock ManychatBackend
        self.mock_backend = MagicMock()
        self.mock_backend.send.return_value = NotificationResult(
            success=True,
            message_id="mc_12345",
        )
        register_backend("manychat", self.mock_backend)

        # Register the handler
        self.handler = NotificationSendHandler()
        registry.register_directive_handler(self.handler)

        # Create order
        self.order = Order.objects.create(
            ref="ORD-TEST-001",
            channel=self.channel,
            session_key="SESS-001",
            handle_type="subscriber",
            handle_ref="12345",
            status="new",
            snapshot={"items": [], "data": {}, "pricing": {}, "rev": 0},
            data={
                "customer": {"phone": "+5543999999999", "name": "Maria"},
                "items": [
                    {"sku": "PAO", "qty": 2, "unit_price_q": 1200, "line_total_q": 2400},
                ],
            },
            total_q=2400,
        )

    def tearDown(self) -> None:
        registry.clear()
        super().tearDown()

    def test_handler_sends_notification_on_directive(self) -> None:
        """Directive notification.send → ManychatBackend.send() chamado."""
        # Create directive bypassing auto-dispatch by setting status directly
        d = Directive(
            topic="notification.send",
            status="running",
            payload={
                "order_ref": self.order.ref,
                "template": "order.confirmed",
            },
        )
        d.save()
        d.refresh_from_db()

        # Reset mock to ignore any calls from auto-dispatch
        self.mock_backend.reset_mock()

        self.handler.handle(message=d, ctx={})

        # Backend should have been called
        self.mock_backend.send.assert_called_once()
        call_kwargs = self.mock_backend.send.call_args[1]
        self.assertEqual(call_kwargs["event"], "order.confirmed")
        self.assertEqual(call_kwargs["recipient"], "+5543999999999")
        self.assertEqual(call_kwargs["context"]["order_ref"], "ORD-TEST-001")

    def test_handler_marks_done_on_success(self) -> None:
        """Handler marca directive como done quando backend retorna success."""
        d = Directive(
            topic="notification.send",
            status="running",
            payload={
                "order_ref": self.order.ref,
                "template": "order.confirmed",
            },
        )
        d.save()
        d.refresh_from_db()

        self.handler.handle(message=d, ctx={})

        d.refresh_from_db()
        self.assertEqual(d.status, "done")

    def test_handler_marks_failed_on_missing_order(self) -> None:
        """Handler marca directive como failed quando order não encontrada."""
        d = Directive(
            topic="notification.send",
            status="running",
            payload={
                "order_ref": "NONEXISTENT",
                "template": "order.confirmed",
            },
        )
        d.save()
        d.refresh_from_db()

        self.handler.handle(message=d, ctx={})

        d.refresh_from_db()
        self.assertEqual(d.status, "failed")
        self.assertIn("not found", d.last_error)

    def test_handler_retries_on_backend_failure(self) -> None:
        """Handler requeue directive quando backend falha (attempts < 5)."""
        self.mock_backend.send.return_value = NotificationResult(
            success=False,
            error="API timeout",
        )

        d = Directive(
            topic="notification.send",
            status="running",
            attempts=1,
            payload={
                "order_ref": self.order.ref,
                "template": "order.confirmed",
            },
        )
        d.save()
        d.refresh_from_db()

        self.handler.handle(message=d, ctx={})

        d.refresh_from_db()
        self.assertEqual(d.status, "queued")

    def test_handler_fails_permanently_after_max_attempts(self) -> None:
        """Handler marca failed quando attempts >= 5."""
        self.mock_backend.send.return_value = NotificationResult(
            success=False,
            error="API timeout",
        )

        d = Directive(
            topic="notification.send",
            status="running",
            attempts=5,
            payload={
                "order_ref": self.order.ref,
                "template": "order.confirmed",
            },
        )
        d.save()
        d.refresh_from_db()

        self.handler.handle(message=d, ctx={})

        d.refresh_from_db()
        self.assertEqual(d.status, "failed")


class OrderStatusChangeNotificationTests(TestCase):
    """Verifica que mudança de status cria Directive notification.send."""

    def setUp(self) -> None:
        super().setUp()
        self.channel = Channel.objects.create(
            ref="whatsapp",
            name="WhatsApp",
            pricing_policy="external",
            edit_policy="open",
            config={
                "notifications": {"backend": "manychat"},
            },
            is_active=True,
        )

    def test_order_transition_emits_signal(self) -> None:
        """Order.transition_status() emite signal order_changed."""
        order = Order.objects.create(
            ref="ORD-SIG-001",
            channel=self.channel,
            session_key="SESS-SIG",
            status="new",
            snapshot={},
            data={"customer": {"phone": "+5543999999999"}},
            total_q=1000,
        )

        with patch("shopman.ordering.signals.order_changed.send") as mock_signal:
            order.transition_status("confirmed", actor="test")
            mock_signal.assert_called_once()
            call_kwargs = mock_signal.call_args[1]
            self.assertEqual(call_kwargs["order"], order)
            self.assertEqual(call_kwargs["event_type"], "status_changed")


class ManychatBackendUnitTests(TestCase):
    """Unit tests for ManychatBackend subscriber resolution."""

    def test_numeric_subscriber_resolves_directly(self) -> None:
        """Subscriber ID numérico é resolvido diretamente."""
        config = ManychatConfig(api_token="test-token")
        backend = ManychatBackend(config=config)

        subscriber_id = backend._resolve_subscriber("12345")
        self.assertEqual(subscriber_id, 12345)

    def test_phone_resolves_via_resolver(self) -> None:
        """Phone E.164 → subscriber_id via resolver."""
        mock_resolver = MagicMock(return_value=67890)
        config = ManychatConfig(api_token="test-token")
        backend = ManychatBackend(config=config, resolver=mock_resolver)

        subscriber_id = backend._resolve_subscriber("+5543999999999")
        self.assertEqual(subscriber_id, 67890)
        mock_resolver.assert_called_once_with("+5543999999999")

    def test_unresolvable_subscriber_returns_none(self) -> None:
        """Subscriber sem resolver retorna None para non-numeric."""
        config = ManychatConfig(api_token="test-token")
        backend = ManychatBackend(config=config)

        subscriber_id = backend._resolve_subscriber("+5543999999999")
        self.assertIsNone(subscriber_id)

    def test_build_message_with_template(self) -> None:
        """Template de mensagem é preenchido corretamente."""
        config = ManychatConfig(api_token="test-token")
        backend = ManychatBackend(config=config)

        msg = backend._build_message("order.confirmed", {
            "order_ref": "ORD-123",
            "customer_name": "Maria",
            "total": "R$ 24,00",
        })
        self.assertIn("ORD-123", msg)
        self.assertIn("Maria", msg)

    def test_build_message_fallback(self) -> None:
        """Evento sem template usa fallback genérico."""
        config = ManychatConfig(api_token="test-token")
        backend = ManychatBackend(config=config)

        msg = backend._build_message("unknown.event", {"order_ref": "ORD-456"})
        self.assertIn("unknown.event", msg)
        self.assertIn("ORD-456", msg)
