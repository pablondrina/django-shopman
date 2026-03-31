"""
Dedicated tests for NotificationSendHandler.

Covers:
- Fallback chain routing (manychat → email by default)
- Recipient resolution per backend type
- Skip logic (backend=none, payment.reminder when paid)
- Retry/failure logic (attempts limit)
- Missing order_ref / order not found
- Backward compat: old 'fallback' string format
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from channels.config import ChannelConfig
from channels.handlers.notification import NotificationSendHandler
from channels.protocols import NotificationResult
from channels.notifications import register_backend, _backends
from channels.topics import NOTIFICATION_SEND
from shopman.ordering.models import Channel, Directive, Order


def _create_directive(**kwargs) -> Directive:
    """Create directive bypassing post_save signal."""
    objs = Directive.objects.bulk_create([Directive(**kwargs)])
    return objs[0]


class FallbackChainRoutingTests(TestCase):
    """Tests for fallback chain routing resolution."""

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
        register_backend("console", self.mock_backend)

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
            "notification_routing": {"backend": "email", "fallback_chain": ["console"]},
        })
        order = Order.objects.create(
            ref="ORD-R1", channel=channel, status="new",
            data={"customer": {"phone": "+5543999999999"}},
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "order_confirmed"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.mock_backend.send.assert_called_once()
        call_kwargs = self.mock_backend.send.call_args[1]
        self.assertEqual(call_kwargs["event"], "order_confirmed")

    def test_routing_from_notifications_backend(self) -> None:
        """Priority 2: Channel.config['notifications']['backend']."""
        channel = self._make_channel(config={
            "notifications": {"backend": "manychat"},
        })
        order = Order.objects.create(
            ref="ORD-R2", channel=channel, status="new",
            handle_type="manychat", handle_ref="sub_123",
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "order_confirmed"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

    def test_default_chain_manychat_then_email(self) -> None:
        """Priority 3: Default chain is manychat → email."""
        channel = self._make_channel(ref="whatsapp", config={})
        order = Order.objects.create(
            ref="ORD-R3", channel=channel, status="new",
            handle_type="manychat", handle_ref="sub_456",
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "test"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

    def test_none_backend_skips_notification(self) -> None:
        """backend=none → done (silently skipped)."""
        channel = self._make_channel(ref="ifood", config={
            "notifications": {"backend": "none", "fallback_chain": []},
        })
        order = Order.objects.create(
            ref="ORD-NONE", channel=channel, status="new",
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "order_confirmed"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.mock_backend.send.assert_not_called()

    def test_old_fallback_string_compat(self) -> None:
        """Old 'fallback' string is converted to chain."""
        failing = MagicMock()
        failing.send = MagicMock(
            return_value=NotificationResult(success=False, error="Down")
        )
        _backends.clear()
        register_backend("manychat", failing)
        register_backend("sms", self.mock_backend)

        channel = self._make_channel(config={
            "notification_routing": {"backend": "manychat", "fallback": "sms"},
        })
        order = Order.objects.create(
            ref="ORD-COMPAT", channel=channel, status="new",
            handle_type="manychat", handle_ref="sub_compat",
            data={"customer": {"phone": "+5543999999999"}},
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "test"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        # manychat failed, sms succeeded
        failing.send.assert_called_once()
        self.mock_backend.send.assert_called_once()


class RecipientResolutionTests(TestCase):
    """Tests for recipient resolution per backend type."""

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
                "notifications": {"backend": "manychat", "fallback_chain": []},
            },
        )
        order = Order.objects.create(
            ref="ORD-MC", channel=channel, status="new",
            handle_type="manychat", handle_ref="subscriber_789",
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "test"},
        )

        self.handler.handle(message=directive, ctx={})

        call_kwargs = self.mock_backend.send.call_args[1]
        self.assertEqual(call_kwargs["recipient"], "subscriber_789")

    def test_manychat_falls_back_to_phone(self) -> None:
        """Manychat without handle_ref uses phone."""
        channel = Channel.objects.create(
            ref="whatsapp", name="WA", config={
                "notifications": {"backend": "manychat", "fallback_chain": []},
            },
        )
        order = Order.objects.create(
            ref="ORD-MC-PHONE", channel=channel, status="new",
            data={"customer": {"phone": "+5543999999999"}},
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "test"},
        )

        self.handler.handle(message=directive, ctx={})

        call_kwargs = self.mock_backend.send.call_args[1]
        self.assertEqual(call_kwargs["recipient"], "+5543999999999")

    def test_email_recipient_prefers_email(self) -> None:
        """Email backend uses customer.email over phone."""
        channel = Channel.objects.create(
            ref="web", name="Web", config={
                "notifications": {"backend": "email", "fallback_chain": []},
            },
        )
        order = Order.objects.create(
            ref="ORD-EMAIL", channel=channel, status="new",
            data={"customer": {"email": "maria@example.com", "phone": "+5543988887777"}},
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "test"},
        )

        self.handler.handle(message=directive, ctx={})

        call_kwargs = self.mock_backend.send.call_args[1]
        self.assertEqual(call_kwargs["recipient"], "maria@example.com")

    def test_phone_recipient_from_customer_data(self) -> None:
        """Non-manychat orders use data['customer']['phone']."""
        channel = Channel.objects.create(
            ref="web", name="Web", config={
                "notifications": {"backend": "email", "fallback_chain": []},
            },
        )
        order = Order.objects.create(
            ref="ORD-PHONE", channel=channel, status="new",
            data={"customer": {"phone": "+5543988887777"}},
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "test"},
        )

        self.handler.handle(message=directive, ctx={})

        call_kwargs = self.mock_backend.send.call_args[1]
        self.assertEqual(call_kwargs["recipient"], "+5543988887777")

    def test_no_recipient_skips_backend_tries_next(self) -> None:
        """No recipient for primary → tries next in chain."""
        channel = Channel.objects.create(
            ref="web", name="Web", config={},  # default chain: manychat → email
        )
        order = Order.objects.create(
            ref="ORD-NOREC", channel=channel, status="new",
            data={"customer": {"email": "found@example.com"}},
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "test"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        # manychat has no recipient (no handle_ref, no phone), email has email
        # so it should succeed via email
        self.assertEqual(directive.status, "done")


class EdgeCaseTests(TestCase):
    """Error handling and special cases."""

    def setUp(self) -> None:
        self.handler = NotificationSendHandler()
        _backends.clear()

    def tearDown(self) -> None:
        _backends.clear()

    def test_missing_order_ref_fails(self) -> None:
        """No order_ref in payload → failed."""
        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"template": "test"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertEqual(directive.last_error, "missing order_ref")

    def test_order_not_found_fails(self) -> None:
        """Nonexistent order → failed."""
        directive = _create_directive(
            topic=NOTIFICATION_SEND,
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
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "payment.reminder"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

    def test_payment_reminder_skipped_when_order_not_new(self) -> None:
        """payment.reminder for confirmed order → done (skipped)."""
        channel = Channel.objects.create(ref="whatsapp", name="WA", config={})
        order = Order.objects.create(
            ref="ORD-CONF", channel=channel, status="confirmed",
            data={"payment": {"status": "pending"}},
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "payment.reminder"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

    def test_fallback_chain_all_fail_retries(self) -> None:
        """All backends in chain fail → queued (retry) until attempts >= 5."""
        failing_backend = MagicMock()
        failing_backend.send = MagicMock(
            return_value=NotificationResult(success=False, error="Down")
        )

        register_backend("manychat", failing_backend)
        register_backend("email", failing_backend)

        channel = Channel.objects.create(
            ref="whatsapp", name="WA", config={
                "notifications": {"backend": "manychat", "fallback_chain": ["email"]},
            },
        )
        order = Order.objects.create(
            ref="ORD-RETRY", channel=channel, status="new",
            handle_type="manychat", handle_ref="sub_retry",
            data={"customer": {"email": "x@x.com"}},
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
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

        register_backend("manychat", failing_backend)

        channel = Channel.objects.create(
            ref="whatsapp", name="WA", config={
                "notifications": {"backend": "manychat", "fallback_chain": []},
            },
        )
        order = Order.objects.create(
            ref="ORD-MAXRETRY", channel=channel, status="new",
            handle_type="manychat", handle_ref="sub_max",
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "test"},
        )
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
                "notifications": {"backend": "email", "fallback_chain": []},
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
            topic=NOTIFICATION_SEND,
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
                "notifications": {"backend": "manychat", "fallback_chain": []},
            },
        )
        order = Order.objects.create(
            ref="ORD-SUBID", channel=channel, status="new",
            handle_type="manychat", handle_ref="sub_context_test",
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "test"},
        )

        self.handler.handle(message=directive, ctx={})

        call_kwargs = mock_backend.send.call_args[1]
        self.assertEqual(call_kwargs["context"]["subscriber_id"], "sub_context_test")


# ── Cancellation hooks (Bug 3) ──


class CancelOrderHooksTests(TestCase):
    """Bug 3 fix: _on_cancelled is called when order transitions to CANCELLED."""

    def test_cancel_order_releases_holds(self):
        """Verify holds are released when order is cancelled."""
        from unittest.mock import MagicMock, patch

        channel = Channel.objects.create(ref="pos", name="POS", config={})
        order = Order.objects.create(
            ref="ORD-CANCEL1", channel=channel, status="cancelled",
            session_key="sess-cancel-1",
            data={"session_key": "sess-cancel-1"},
        )

        mock_backend = MagicMock()
        mock_backend.release_holds_for_reference = MagicMock(return_value=3)

        with patch("channels.setup._load_stock_backend", return_value=mock_backend):
            from channels.hooks import _on_cancelled
            _on_cancelled(order)

        mock_backend.release_holds_for_reference.assert_called_once_with("sess-cancel-1")

    def test_cancel_order_sends_notification(self):
        """Verify notification directive is created when cancellation has no reason."""
        channel = Channel.objects.create(ref="pos", name="POS", config={})
        order = Order.objects.create(
            ref="ORD-CANCEL2", channel=channel, status="cancelled",
            data={},
        )

        from unittest.mock import patch
        with patch("channels.setup._load_stock_backend", return_value=None):
            from channels.hooks import _on_cancelled
            _on_cancelled(order)

        directive = Directive.objects.filter(
            topic=NOTIFICATION_SEND,
            payload__order_ref="ORD-CANCEL2",
        ).first()
        self.assertIsNotNone(directive)
        self.assertEqual(directive.payload["template"], "order_cancelled")

    def test_lifecycle_dispatcher_calls_on_cancelled(self):
        """Verify on_order_lifecycle dispatches to _on_cancelled for CANCELLED status."""
        from unittest.mock import patch

        channel = Channel.objects.create(ref="pos", name="POS", config={})
        order = Order.objects.create(
            ref="ORD-CANCEL3", channel=channel, status="cancelled",
            data={},
        )

        with patch("channels.hooks._on_cancelled") as mock_on_cancelled:
            from channels.hooks import on_order_lifecycle
            on_order_lifecycle(
                sender=None, order=order,
                event_type="status_changed", actor="test",
            )

        mock_on_cancelled.assert_called_once_with(order)


# ── Phone-first fallback chain ──


class PhoneFirstFallbackTests(TestCase):
    """Fallback chain must be phone-first: manychat → sms → email."""

    def test_default_config_fallback_is_sms_then_email(self) -> None:
        """ChannelConfig default fallback_chain includes sms before email."""
        config = ChannelConfig()
        self.assertEqual(config.notifications.fallback_chain, ["sms", "email"])

    def test_remote_preset_fallback_is_sms_then_email(self) -> None:
        """remote() preset fallback includes sms before email."""
        from channels.presets import remote

        config = ChannelConfig.from_dict(remote())
        self.assertEqual(config.notifications.fallback_chain, ["sms", "email"])

    def test_default_handler_chain_includes_sms(self) -> None:
        """Default chain (no config) is manychat → sms → email."""
        handler = NotificationSendHandler()
        _backends.clear()

        mock_backend = MagicMock()
        mock_backend.send = MagicMock(
            return_value=NotificationResult(success=True, message_id="msg-1")
        )
        register_backend("manychat", mock_backend)
        register_backend("sms", mock_backend)
        register_backend("email", mock_backend)

        channel = Channel.objects.create(ref="default", name="Default", config={})
        order = Order.objects.create(
            ref="ORD-PHONE-FIRST", channel=channel, status="new",
            handle_type="manychat", handle_ref="sub_pf",
        )

        chain = handler._resolve_backend_chain(order)
        self.assertEqual(chain, ["manychat", "sms", "email"])

        _backends.clear()

    def test_sms_used_when_manychat_fails(self) -> None:
        """When manychat fails, sms is tried before email."""
        _backends.clear()
        failing = MagicMock()
        failing.send = MagicMock(
            return_value=NotificationResult(success=False, error="Down")
        )
        success = MagicMock()
        success.send = MagicMock(
            return_value=NotificationResult(success=True, message_id="sms-1")
        )
        email = MagicMock()
        email.send = MagicMock(
            return_value=NotificationResult(success=True, message_id="email-1")
        )

        register_backend("manychat", failing)
        register_backend("sms", success)
        register_backend("email", email)

        handler = NotificationSendHandler()
        channel = Channel.objects.create(
            ref="wa-sms", name="WA-SMS",
            config={"notifications": {"backend": "manychat", "fallback_chain": ["sms", "email"]}},
        )
        order = Order.objects.create(
            ref="ORD-SMS-FB", channel=channel, status="new",
            handle_type="manychat", handle_ref="sub_sms",
            data={"customer": {"phone": "+5543999999999"}},
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "order_confirmed"},
        )

        handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        # manychat failed, sms succeeded — email not called
        failing.send.assert_called_once()
        success.send.assert_called_once()
        email.send.assert_not_called()

        _backends.clear()


# ── on_processing notification ──


class ProcessingNotificationTests(TestCase):
    """Status 'processing' must trigger a notification directive."""

    def test_pos_preset_has_on_processing(self) -> None:
        """pos() preset includes notification on processing."""
        from channels.presets import pos

        config = ChannelConfig.from_dict(pos())
        self.assertEqual(
            config.pipeline.on_processing,
            [f"{NOTIFICATION_SEND}:order_processing"],
        )

    def test_remote_preset_has_on_processing(self) -> None:
        """remote() preset includes notification on processing."""
        from channels.presets import remote

        config = ChannelConfig.from_dict(remote())
        self.assertEqual(
            config.pipeline.on_processing,
            [f"{NOTIFICATION_SEND}:order_processing"],
        )

    def test_marketplace_preset_no_on_processing(self) -> None:
        """marketplace() preset has no on_processing (notifications disabled)."""
        from channels.presets import marketplace

        config = ChannelConfig.from_dict(marketplace())
        self.assertEqual(config.pipeline.on_processing, [])

    def test_processing_creates_notification_directive(self) -> None:
        """Transitioning to processing creates a notification directive via hooks."""
        from channels.presets import remote

        channel = Channel.objects.create(
            ref="wa-proc", name="WA Processing", config=remote(),
        )
        order = Order.objects.create(
            ref="ORD-PROC", channel=channel, status="processing",
            data={},
        )

        from channels.hooks import on_order_lifecycle
        on_order_lifecycle(
            sender=None, order=order,
            event_type="status_changed", actor="test",
        )

        directive = Directive.objects.filter(
            topic=NOTIFICATION_SEND,
            payload__order_ref="ORD-PROC",
        ).first()
        self.assertIsNotNone(directive)
        self.assertEqual(directive.payload["template"], "order_processing")

    def test_email_backend_has_processing_template(self) -> None:
        """EmailBackend has subject + body templates for order_processing."""
        from channels.backends.notification_email import EmailBackend

        backend = EmailBackend()
        self.assertIn("order_processing", backend.SUBJECT_TEMPLATES)
        self.assertIn("order_processing", backend.BODY_TEMPLATES)
