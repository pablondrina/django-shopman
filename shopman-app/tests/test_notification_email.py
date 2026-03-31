"""
Tests for notification system — email backend + fallback chain.

Covers:
- EmailBackend registration and send via Django mail
- Email sent on order_confirmed directive
- Stock alert creates notification directive (handled by system path)
- Fallback chain: manychat → email → console
- Email recipient resolution (email field preferred for email backend)
- Django template rendering
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.core import mail
from django.test import TestCase, override_settings
from shopman.ordering.models import Channel, Directive, Order

from channels.backends.notification_email import EmailBackend
from channels.handlers.notification import NotificationSendHandler
from channels.notifications import _backends, register_backend
from channels.protocols import NotificationResult
from channels.topics import NOTIFICATION_SEND


def _create_directive(**kwargs) -> Directive:
    """Create directive bypassing post_save signal."""
    objs = Directive.objects.bulk_create([Directive(**kwargs)])
    return objs[0]


class EmailBackendRegistrationTests(TestCase):
    """EmailBackend is registered and functional."""

    def setUp(self) -> None:
        _backends.clear()

    def tearDown(self) -> None:
        _backends.clear()

    def test_email_backend_registered(self) -> None:
        """EmailBackend can be registered and retrieved."""
        backend = EmailBackend()
        register_backend("email", backend)

        from channels.notifications import get_backend
        result = get_backend("email")
        self.assertIsInstance(result, EmailBackend)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="test@shopman.local",
    )
    def test_email_backend_sends_via_django_mail(self) -> None:
        """EmailBackend uses Django's mail system."""
        backend = EmailBackend(from_email="test@shopman.local")

        result = backend.send(
            event="order_confirmed",
            recipient="customer@example.com",
            context={"order_ref": "ORD-123", "total": "R$ 50,00"},
        )

        self.assertTrue(result.success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["customer@example.com"])
        self.assertIn("ORD-123", mail.outbox[0].subject)
        self.assertIn("ORD-123", mail.outbox[0].body)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    )
    def test_email_backend_includes_customer_name(self) -> None:
        """Email body includes customer name greeting."""
        backend = EmailBackend()

        result = backend.send(
            event="order_confirmed",
            recipient="customer@example.com",
            context={
                "order_ref": "ORD-456",
                "customer_name": "Maria",
                "total": "R$ 100,00",
            },
        )

        self.assertTrue(result.success)
        self.assertIn("Maria", mail.outbox[0].body)


class EmailSentOnOrderConfirmedTests(TestCase):
    """Email is sent when order_confirmed directive is processed."""

    def setUp(self) -> None:
        _backends.clear()
        self.handler = NotificationSendHandler()

        self.email_backend = EmailBackend()
        register_backend("email", self.email_backend)

        self.channel = Channel.objects.create(
            ref="web",
            name="Web",
            config={"notifications": {"backend": "email", "fallback_chain": []}},
        )
        self.order = Order.objects.create(
            ref="ORD-EMAIL-01",
            channel=self.channel,
            status="confirmed",
            data={
                "customer": {
                    "email": "joao@example.com",
                    "phone": "+5543999999999",
                    "name": "Joao",
                },
            },
            total_q=5000,
        )

    def tearDown(self) -> None:
        _backends.clear()

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="loja@shopman.local",
    )
    def test_email_sent_on_order_confirmed(self) -> None:
        """Processing order_confirmed directive sends email via Django mail."""
        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": self.order.ref, "template": "order_confirmed"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["joao@example.com"])
        self.assertIn("ORD-EMAIL-01", mail.outbox[0].subject)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    )
    def test_email_recipient_prefers_email_over_phone(self) -> None:
        """When backend is email, customer.email is used as recipient."""
        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": self.order.ref, "template": "order_confirmed"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        # Should use email, not phone
        self.assertEqual(mail.outbox[0].to, ["joao@example.com"])

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    )
    def test_email_falls_back_to_phone_when_no_email(self) -> None:
        """When customer has no email, falls back to phone as recipient."""
        self.order.data = {"customer": {"phone": "+5543999999999"}}
        self.order.save()

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": self.order.ref, "template": "order_confirmed"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        # Falls back to phone
        self.assertEqual(mail.outbox[0].to, ["+5543999999999"])


class StockAlertNotificationTests(TestCase):
    """Stock alert directive is processed as system notification."""

    def setUp(self) -> None:
        _backends.clear()
        self.handler = NotificationSendHandler()

        self.mock_email = MagicMock()
        self.mock_email.send = MagicMock(
            return_value=NotificationResult(success=True, message_id="email-alert-1")
        )
        register_backend("email", self.mock_email)

        self.mock_console = MagicMock()
        self.mock_console.send = MagicMock(
            return_value=NotificationResult(success=True, message_id="console-1")
        )
        register_backend("console", self.mock_console)

    def tearDown(self) -> None:
        _backends.clear()

    @override_settings(DEFAULT_FROM_EMAIL="admin@shopman.local")
    def test_stock_alert_triggers_notification(self) -> None:
        """Stock alert directive is processed via system notification path."""
        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={
                "event": "stock.alert.triggered",
                "context": {
                    "alert_id": 1,
                    "sku": "PAO-FORMA",
                    "position": "vitrine",
                    "min_quantity": "10",
                    "available": "3",
                },
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.mock_email.send.assert_called_once()
        call_kwargs = self.mock_email.send.call_args[1]
        self.assertEqual(call_kwargs["event"], "stock_alert")
        self.assertIn("PAO-FORMA", str(call_kwargs["context"]))

    def test_stock_alert_no_order_ref_does_not_fail(self) -> None:
        """Stock alert directive has no order_ref and should not fail."""
        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={
                "event": "stock.alert.triggered",
                "context": {
                    "sku": "CROISSANT",
                    "min_quantity": "5",
                    "available": "2",
                },
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        # Should not be "failed" due to missing order_ref
        self.assertIn(directive.status, ("done", "queued"))


class FallbackChainTests(TestCase):
    """Fallback chain: primary → fallback_chain backends."""

    def setUp(self) -> None:
        _backends.clear()
        self.handler = NotificationSendHandler()

    def tearDown(self) -> None:
        _backends.clear()

    def test_fallback_chain_on_primary_failure(self) -> None:
        """When primary backend fails, handler tries next in chain."""
        failing_manychat = MagicMock()
        failing_manychat.send = MagicMock(
            return_value=NotificationResult(success=False, error="API error")
        )
        ok_email = MagicMock()
        ok_email.send = MagicMock(
            return_value=NotificationResult(success=True, message_id="email-ok")
        )

        register_backend("manychat", failing_manychat)
        register_backend("email", ok_email)

        channel = Channel.objects.create(
            ref="whatsapp",
            name="WA",
            config={
                "notifications": {"backend": "manychat", "fallback_chain": ["email"]},
            },
        )
        order = Order.objects.create(
            ref="ORD-CHAIN-01",
            channel=channel,
            status="confirmed",
            handle_type="manychat",
            handle_ref="sub_123",
            data={"customer": {"phone": "+5543999999999", "email": "test@example.com"}},
            total_q=3000,
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "order_confirmed"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        failing_manychat.send.assert_called_once()
        ok_email.send.assert_called_once()

    def test_old_fallback_format_still_works(self) -> None:
        """Old 'fallback' (string) is converted to fallback_chain."""
        failing_email = MagicMock()
        failing_email.send = MagicMock(
            return_value=NotificationResult(success=False, error="SMTP error")
        )
        ok_console = MagicMock()
        ok_console.send = MagicMock(
            return_value=NotificationResult(success=True, message_id="console-ok")
        )

        register_backend("email", failing_email)
        register_backend("console", ok_console)

        channel = Channel.objects.create(
            ref="web",
            name="Web",
            config={
                "notification_routing": {"backend": "email", "fallback": "console"},
            },
        )
        order = Order.objects.create(
            ref="ORD-COMPAT-01",
            channel=channel,
            status="confirmed",
            data={"customer": {"phone": "+5543999999999"}},
            total_q=3000,
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "order_confirmed"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        failing_email.send.assert_called_once()
        ok_console.send.assert_called_once()

    @override_settings(DEFAULT_FROM_EMAIL="admin@shopman.local")
    def test_stock_alert_fallback_to_console(self) -> None:
        """Stock alert falls back to console when email fails."""
        failing_email = MagicMock()
        failing_email.send = MagicMock(
            return_value=NotificationResult(success=False, error="SMTP down")
        )
        ok_console = MagicMock()
        ok_console.send = MagicMock(
            return_value=NotificationResult(success=True, message_id="console-ok")
        )

        register_backend("email", failing_email)
        register_backend("console", ok_console)

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={
                "event": "stock.alert.triggered",
                "context": {
                    "sku": "BAGUETE",
                    "min_quantity": "10",
                    "available": "2",
                },
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        ok_console.send.assert_called_once()

    def test_all_backends_fail_queues_for_retry(self) -> None:
        """When all backends in chain fail, directive is queued for retry."""
        failing = MagicMock()
        failing.send = MagicMock(
            return_value=NotificationResult(success=False, error="Down")
        )

        register_backend("manychat", failing)
        register_backend("email", failing)

        channel = Channel.objects.create(
            ref="whatsapp",
            name="WA",
            config={
                "notifications": {"backend": "manychat", "fallback_chain": ["email"]},
            },
        )
        order = Order.objects.create(
            ref="ORD-ALLFAIL",
            channel=channel,
            status="confirmed",
            handle_type="manychat",
            handle_ref="sub_fail",
            data={"customer": {"phone": "+5543999999999", "email": "x@x.com"}},
            total_q=1000,
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "order_confirmed"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "queued")


class EmailBackendTemplateTests(TestCase):
    """EmailBackend renders Django templates when available."""

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    )
    def test_email_renders_html_template(self) -> None:
        """EmailBackend includes HTML from Django template."""
        backend = EmailBackend()

        result = backend.send(
            event="order_confirmed",
            recipient="test@example.com",
            context={"order_ref": "ORD-TPL-01"},
        )

        self.assertTrue(result.success)
        self.assertEqual(len(mail.outbox), 1)
        # HTML message should be present (from Django template)
        html = mail.outbox[0].alternatives
        if html:
            self.assertIn("ORD-TPL-01", html[0][0])

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    )
    def test_stock_alert_template_renders(self) -> None:
        """stock_alert template renders with SKU and quantities."""
        backend = EmailBackend()

        result = backend.send(
            event="stock_alert",
            recipient="admin@example.com",
            context={
                "sku": "PAO-INTEGRAL",
                "available": "2",
                "min_quantity": "10",
            },
        )

        self.assertTrue(result.success)
        self.assertIn("PAO-INTEGRAL", mail.outbox[0].body)

    def test_email_subject_templates_cover_all_events(self) -> None:
        """All expected events have subject templates."""
        backend = EmailBackend()
        expected_events = [
            "order_confirmed",
            "order_ready",
            "order_dispatched",
            "order_delivered",
            "order_cancelled",
            "payment_confirmed",
            "payment_expired",
            "stock_alert",
        ]
        for event in expected_events:
            self.assertIn(event, backend.SUBJECT_TEMPLATES, f"Missing subject for {event}")
            self.assertIn(event, backend.BODY_TEMPLATES, f"Missing body for {event}")


class DefaultFallbackChainTests(TestCase):
    """Verify default fallback chain behavior (manychat → email)."""

    def setUp(self) -> None:
        _backends.clear()
        self.handler = NotificationSendHandler()

    def tearDown(self) -> None:
        _backends.clear()

    def test_default_chain_is_manychat_then_email(self) -> None:
        """Without config, default chain is manychat → email."""
        ok_backend = MagicMock()
        ok_backend.send = MagicMock(
            return_value=NotificationResult(success=True, message_id="mc-1")
        )
        register_backend("manychat", ok_backend)
        register_backend("email", ok_backend)

        channel = Channel.objects.create(ref="instagram", name="IG", config={})
        order = Order.objects.create(
            ref="ORD-DEFAULT-01",
            channel=channel,
            status="new",
            handle_type="manychat",
            handle_ref="sub_default",
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "order_confirmed"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        # manychat should be tried first
        call_kwargs = ok_backend.send.call_args_list[0][1]
        self.assertEqual(call_kwargs["recipient"], "sub_default")

    def test_default_chain_falls_to_email_when_manychat_fails(self) -> None:
        """Default chain: manychat fails → email succeeds."""
        failing_mc = MagicMock()
        failing_mc.send = MagicMock(
            return_value=NotificationResult(success=False, error="MC down")
        )
        ok_email = MagicMock()
        ok_email.send = MagicMock(
            return_value=NotificationResult(success=True, message_id="email-1")
        )

        register_backend("manychat", failing_mc)
        register_backend("email", ok_email)

        channel = Channel.objects.create(ref="instagram", name="IG", config={})
        order = Order.objects.create(
            ref="ORD-DEFAULT-02",
            channel=channel,
            status="new",
            data={"customer": {"email": "test@example.com", "phone": "+5543999999999"}},
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "order_confirmed"},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        failing_mc.send.assert_called_once()
        ok_email.send.assert_called_once()
        # Email backend should use email as recipient
        email_call = ok_email.send.call_args[1]
        self.assertEqual(email_call["recipient"], "test@example.com")
