"""
Dedicated tests for NotificationSendHandler.

Covers:
- Routing by channel config (new format, legacy, defaults)
- Recipient resolution (manychat, phone, fallback)
- Skip logic (backend=none, payment.reminder when paid)
- Fallback backends
- Retry/failure logic (attempts limit)
- Missing order_ref / order not found
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from shopman.notifications.handlers import NotificationSendHandler, DEFAULT_ROUTING
from shopman.notifications.protocols import NotificationResult
from shopman.notifications.service import register_backend, _backends
from shopman.ordering.models import Channel, Directive, Order


def _create_directive(**kwargs) -> Directive:
    """Create directive bypassing post_save signal."""
    objs = Directive.objects.bulk_create([Directive(**kwargs)])
    return objs[0]


class NotificationSendHandlerRoutingTests(TestCase):
    """Tests for routing resolution logic."""

    def setUp(self) -> None:
        self.handler = NotificationSendHandler()
        self.mock_backend = MagicMock()
        self.mock_backend.send = MagicMock(
            return_value=NotificationResult(success=True, message_id="msg-1")
        )
        _backends.clear()
        register_backend("manychat", self.mock_backend)
        register_backend("email", self.mock_backend)
        register_backend("sms", self.mock_backend)

    def tearDown(self) -> None:
        _backends.clear()

    def _make_channel(self, ref="whatsapp", config=None) -> Channel:
        return Channel.objects.create(
            ref=ref,
            name=f"Channel {ref}",
            config=config or {},
        )

    def test_routing_from_notification_routing_config(self) -> None:
        """Priority 1: Channel.config['notification_routing']."""
        channel = self._make_channel(config={
            "notification_routing": {"backend": "email", "fallback": "sms"},
        })
        order = Order.objects.create(
            ref="ORD-R1", channel=channel, status="new",
            data={"customer": {"phone": "+5543999999999"}},
        )

        directive = _create_directive(
            topic="notification.send",
            payload={"order_ref": order.ref, "template": "order_confirmed"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.mock_backend.send.assert_called_once()
        call_kwargs = self.mock_backend.send.call_args[1]
        self.assertEqual(call_kwargs["event"], "order_confirmed")

    def test_routing_from_legacy_notifications_backend(self) -> None:
        """Priority 2: Channel.config['notifications']['backend']."""
        channel = self._make_channel(config={
            "notifications": {"backend": "manychat"},
        })
        order = Order.objects.create(
            ref="ORD-R2", channel=channel, status="new",
            handle_type="manychat", handle_ref="sub_123",
        )

        directive = _create_directive(
            topic="notification.send",
            payload={"order_ref": order.ref, "template": "order_confirmed"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

    def test_routing_from_default_whatsapp(self) -> None:
        """Priority 3: DEFAULT_ROUTING for whatsapp → manychat."""
        channel = self._make_channel(ref="whatsapp", config={})
        order = Order.objects.create(
            ref="ORD-R3", channel=channel, status="new",
            handle_type="manychat", handle_ref="sub_456",
        )

        directive = _create_directive(
            topic="notification.send",
            payload={"order_ref": order.ref, "template": "test"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

    def test_balcao_channel_skips_notification(self) -> None:
        """Balcão channel → backend=none → done (silently skipped)."""
        channel = self._make_channel(ref="balcao", config={})
        order = Order.objects.create(
            ref="ORD-BALCAO", channel=channel, status="new",
        )

        directive = _create_directive(
            topic="notification.send",
            payload={"order_ref": order.ref, "template": "order_confirmed"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.mock_backend.send.assert_not_called()

    def test_ifood_channel_skips_notification(self) -> None:
        """iFood channel → backend=none → done."""
        channel = self._make_channel(ref="ifood", config={})
        order = Order.objects.create(
            ref="ORD-IFOOD", channel=channel, status="new",
        )

        directive = _create_directive(
            topic="notification.send",
            payload={"order_ref": order.ref, "template": "order_confirmed"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")


class NotificationSendHandlerRecipientTests(TestCase):
    """Tests for recipient resolution logic."""

    def setUp(self) -> None:
        self.handler = NotificationSendHandler()
        self.mock_backend = MagicMock()
        self.mock_backend.send = MagicMock(
            return_value=NotificationResult(success=True, message_id="msg-1")
        )
        _backends.clear()
        register_backend("manychat", self.mock_backend)
        register_backend("email", self.mock_backend)

    def tearDown(self) -> None:
        _backends.clear()

    def test_manychat_recipient_is_handle_ref(self) -> None:
        """Manychat orders use handle_ref as recipient."""
        channel = Channel.objects.create(
            ref="whatsapp", name="WA", config={
                "notification_routing": {"backend": "manychat"},
            },
        )
        order = Order.objects.create(
            ref="ORD-MC", channel=channel, status="new",
            handle_type="manychat", handle_ref="subscriber_789",
        )

        directive = _create_directive(
            topic="notification.send",
            payload={"order_ref": order.ref, "template": "test"},
        )

        self.handler.handle(message=directive, ctx={})

        call_kwargs = self.mock_backend.send.call_args[1]
        self.assertEqual(call_kwargs["recipient"], "subscriber_789")

    def test_phone_recipient_from_customer_data(self) -> None:
        """Non-manychat orders use data['customer']['phone']."""
        channel = Channel.objects.create(
            ref="web", name="Web", config={
                "notification_routing": {"backend": "email"},
            },
        )
        order = Order.objects.create(
            ref="ORD-PHONE", channel=channel, status="new",
            data={"customer": {"phone": "+5543988887777"}},
        )

        directive = _create_directive(
            topic="notification.send",
            payload={"order_ref": order.ref, "template": "test"},
        )

        self.handler.handle(message=directive, ctx={})

        call_kwargs = self.mock_backend.send.call_args[1]
        self.assertEqual(call_kwargs["recipient"], "+5543988887777")

    def test_phone_recipient_fallback_customer_phone(self) -> None:
        """Fallback to data['customer_phone'] if no data['customer']['phone']."""
        channel = Channel.objects.create(
            ref="web", name="Web", config={
                "notification_routing": {"backend": "email"},
            },
        )
        order = Order.objects.create(
            ref="ORD-FALL", channel=channel, status="new",
            data={"customer_phone": "+5543977776666"},
        )

        directive = _create_directive(
            topic="notification.send",
            payload={"order_ref": order.ref, "template": "test"},
        )

        self.handler.handle(message=directive, ctx={})

        call_kwargs = self.mock_backend.send.call_args[1]
        self.assertEqual(call_kwargs["recipient"], "+5543977776666")

    def test_no_recipient_marks_failed(self) -> None:
        """No recipient resolvable → failed."""
        channel = Channel.objects.create(
            ref="web", name="Web", config={
                "notification_routing": {"backend": "email"},
            },
        )
        order = Order.objects.create(
            ref="ORD-NOREC", channel=channel, status="new", data={},
        )

        directive = _create_directive(
            topic="notification.send",
            payload={"order_ref": order.ref, "template": "test"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertEqual(directive.last_error, "No recipient found")


class NotificationSendHandlerEdgeCaseTests(TestCase):
    """Error handling and special cases."""

    def setUp(self) -> None:
        self.handler = NotificationSendHandler()
        _backends.clear()

    def tearDown(self) -> None:
        _backends.clear()

    def test_missing_order_ref_fails(self) -> None:
        """No order_ref in payload → failed."""
        directive = _create_directive(
            topic="notification.send",
            payload={"template": "test"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertEqual(directive.last_error, "missing order_ref")

    def test_order_not_found_fails(self) -> None:
        """Nonexistent order → failed."""
        directive = _create_directive(
            topic="notification.send",
            payload={"order_ref": "NONEXISTENT", "template": "test"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertIn("Order not found", directive.last_error)

    def test_payment_reminder_skipped_when_captured(self) -> None:
        """payment.reminder for already-paid order → done (skipped)."""
        channel = Channel.objects.create(ref="whatsapp", name="WA", config={})
        order = Order.objects.create(
            ref="ORD-PAID", channel=channel, status="new",
            data={"payment": {"status": "captured"}},
        )

        directive = _create_directive(
            topic="notification.send",
            payload={"order_ref": order.ref, "template": "payment.reminder"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

    def test_payment_reminder_skipped_when_order_not_new(self) -> None:
        """payment.reminder for confirmed order → done (skipped)."""
        channel = Channel.objects.create(
            ref="whatsapp", name="WA", config={
                "order_flow": {
                    "transitions": {"new": ["confirmed"], "confirmed": [], "cancelled": []},
                    "terminal_statuses": ["cancelled"],
                },
            },
        )
        order = Order.objects.create(
            ref="ORD-CONF", channel=channel, status="confirmed",
            data={"payment": {"status": "pending"}},
        )

        directive = _create_directive(
            topic="notification.send",
            payload={"order_ref": order.ref, "template": "payment.reminder"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

    def test_fallback_backend_on_primary_failure(self) -> None:
        """Primary fails → try fallback → success."""
        failing_backend = MagicMock()
        failing_backend.send = MagicMock(
            return_value=NotificationResult(success=False, error="Primary down")
        )
        ok_backend = MagicMock()
        ok_backend.send = MagicMock(
            return_value=NotificationResult(success=True, message_id="fallback-1")
        )

        register_backend("manychat", failing_backend)
        register_backend("sms", ok_backend)

        channel = Channel.objects.create(
            ref="whatsapp", name="WA", config={
                "notification_routing": {"backend": "manychat", "fallback": "sms"},
            },
        )
        order = Order.objects.create(
            ref="ORD-FALLBACK", channel=channel, status="new",
            handle_type="manychat", handle_ref="sub_test",
        )

        directive = _create_directive(
            topic="notification.send",
            payload={"order_ref": order.ref, "template": "order_confirmed"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        ok_backend.send.assert_called_once()

    def test_both_backends_fail_retries_up_to_5(self) -> None:
        """Both primary and fallback fail → queued (retry) until attempts >= 5."""
        failing_backend = MagicMock()
        failing_backend.send = MagicMock(
            return_value=NotificationResult(success=False, error="Down")
        )

        register_backend("manychat", failing_backend)
        register_backend("sms", failing_backend)

        channel = Channel.objects.create(
            ref="whatsapp", name="WA", config={
                "notification_routing": {"backend": "manychat", "fallback": "sms"},
            },
        )
        order = Order.objects.create(
            ref="ORD-RETRY", channel=channel, status="new",
            handle_type="manychat", handle_ref="sub_retry",
        )

        # First attempt → queued
        directive = _create_directive(
            topic="notification.send",
            payload={"order_ref": order.ref, "template": "test"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "queued")
        self.assertEqual(directive.last_error, "Down")

    def test_max_attempts_reached_marks_failed(self) -> None:
        """After 5 attempts → failed."""
        failing_backend = MagicMock()
        failing_backend.send = MagicMock(
            return_value=NotificationResult(success=False, error="Permanent failure")
        )

        register_backend("email", failing_backend)

        channel = Channel.objects.create(
            ref="web", name="Web", config={
                "notification_routing": {"backend": "email"},
            },
        )
        order = Order.objects.create(
            ref="ORD-MAXRETRY", channel=channel, status="new",
            data={"customer": {"phone": "+5543999999999"}},
        )

        directive = _create_directive(
            topic="notification.send",
            payload={"order_ref": order.ref, "template": "test"},
        )
        # Simulate 5 previous attempts
        directive.attempts = 5
        directive.save()

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")

    def test_context_includes_payment_data(self) -> None:
        """Context sent to backend includes payment data when present."""
        mock_backend = MagicMock()
        mock_backend.send = MagicMock(
            return_value=NotificationResult(success=True, message_id="msg-ctx")
        )
        register_backend("email", mock_backend)

        channel = Channel.objects.create(
            ref="web", name="Web", config={
                "notification_routing": {"backend": "email"},
            },
        )
        order = Order.objects.create(
            ref="ORD-CTX", channel=channel, status="new",
            data={
                "customer": {"phone": "+5543999999999"},
                "payment": {"intent_id": "pi_test", "status": "pending", "amount_q": 5000},
            },
        )

        directive = _create_directive(
            topic="notification.send",
            payload={"order_ref": order.ref, "template": "payment_confirmed"},
        )

        self.handler.handle(message=directive, ctx={})

        call_kwargs = mock_backend.send.call_args[1]
        self.assertIn("payment", call_kwargs["context"])
        self.assertEqual(call_kwargs["context"]["payment"]["intent_id"], "pi_test")

    def test_manychat_context_includes_subscriber_id(self) -> None:
        """Manychat backend gets subscriber_id in context."""
        mock_backend = MagicMock()
        mock_backend.send = MagicMock(
            return_value=NotificationResult(success=True, message_id="msg-mc")
        )
        register_backend("manychat", mock_backend)

        channel = Channel.objects.create(
            ref="whatsapp", name="WA", config={
                "notification_routing": {"backend": "manychat"},
            },
        )
        order = Order.objects.create(
            ref="ORD-SUBID", channel=channel, status="new",
            handle_type="manychat", handle_ref="sub_context_test",
        )

        directive = _create_directive(
            topic="notification.send",
            payload={"order_ref": order.ref, "template": "test"},
        )

        self.handler.handle(message=directive, ctx={})

        call_kwargs = mock_backend.send.call_args[1]
        self.assertEqual(call_kwargs["context"]["subscriber_id"], "sub_context_test")
