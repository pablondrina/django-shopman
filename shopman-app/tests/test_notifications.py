"""
Tests for contrib/notifications module.

Covers:
- NotificationService (register_backend, get_backend, notify)
- ConsoleBackend
- WebhookBackend
"""

from __future__ import annotations

from io import StringIO
from unittest.mock import Mock, patch, MagicMock
from urllib.error import URLError, HTTPError

from django.test import TestCase, override_settings

from shopman.notifications.backends.console import ConsoleBackend
from shopman.notifications.backends.email import EmailBackend
from shopman.notifications.backends.sms import TwilioSMSBackend
from shopman.notifications.backends.webhook import WebhookBackend
from shopman.notifications.backends.whatsapp import WhatsAppBackend
from shopman.notifications.protocols import NotificationResult
from shopman.notifications import service


class NotificationServiceTests(TestCase):
    """Tests for notification service functions."""

    def setUp(self) -> None:
        # Clear backends registry before each test
        service._backends.clear()

    def tearDown(self) -> None:
        service._backends.clear()

    def test_register_backend(self) -> None:
        """Should register a backend in the registry."""
        mock_backend = Mock()
        service.register_backend("test", mock_backend)

        self.assertIn("test", service._backends)
        self.assertEqual(service._backends["test"], mock_backend)

    def test_get_backend_by_name(self) -> None:
        """Should return backend by name."""
        mock_backend = Mock()
        service.register_backend("mybackend", mock_backend)

        result = service.get_backend("mybackend")

        self.assertEqual(result, mock_backend)

    def test_get_backend_returns_none_for_unknown(self) -> None:
        """Should return None for unknown backend."""
        result = service.get_backend("nonexistent")

        self.assertIsNone(result)

    @override_settings(SHOPMAN_NOTIFICATIONS={"default_backend": "console"})
    def test_get_backend_uses_default_from_settings(self) -> None:
        """Should use default_backend from settings when name is None."""
        console_backend = Mock()
        service.register_backend("console", console_backend)

        result = service.get_backend(None)

        self.assertEqual(result, console_backend)

    @override_settings(SHOPMAN_NOTIFICATIONS={})
    def test_get_backend_defaults_to_console(self) -> None:
        """Should default to 'console' when no default_backend in settings."""
        console_backend = Mock()
        service.register_backend("console", console_backend)

        result = service.get_backend(None)

        self.assertEqual(result, console_backend)

    def test_notify_returns_error_when_backend_not_found(self) -> None:
        """Should return error result when backend not found."""
        result = service.notify(
            event="test.event",
            recipient="+5511999999999",
            context={"key": "value"},
            backend="nonexistent",
        )

        self.assertFalse(result.success)
        self.assertIn("Backend not found", result.error)

    def test_notify_returns_error_when_default_backend_not_found(self) -> None:
        """Should return error when default backend not configured."""
        result = service.notify(
            event="test.event",
            recipient="+5511999999999",
            context={},
        )

        self.assertFalse(result.success)
        self.assertIn("not found", result.error)

    def test_notify_calls_backend_send(self) -> None:
        """Should call backend.send with correct parameters."""
        mock_backend = Mock()
        mock_backend.send.return_value = NotificationResult(
            success=True,
            message_id="MSG-001",
        )
        service.register_backend("test", mock_backend)

        result = service.notify(
            event="order.confirmed",
            recipient="+5511999999999",
            context={"order_ref": "ORD-123"},
            backend="test",
        )

        self.assertTrue(result.success)
        mock_backend.send.assert_called_once_with(
            event="order.confirmed",
            recipient="+5511999999999",
            context={"order_ref": "ORD-123"},
        )

    def test_notify_handles_backend_failure(self) -> None:
        """Should handle failed notification from backend."""
        mock_backend = Mock()
        mock_backend.send.return_value = NotificationResult(
            success=False,
            error="delivery_failed",
        )
        service.register_backend("test", mock_backend)

        result = service.notify(
            event="order.confirmed",
            recipient="+5511999999999",
            context={},
            backend="test",
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, "delivery_failed")

    def test_notify_handles_backend_exception(self) -> None:
        """Should catch exceptions from backend and return error result."""
        mock_backend = Mock()
        mock_backend.send.side_effect = Exception("Connection timeout")
        service.register_backend("test", mock_backend)

        result = service.notify(
            event="order.confirmed",
            recipient="+5511999999999",
            context={},
            backend="test",
        )

        self.assertFalse(result.success)
        self.assertIn("Connection timeout", result.error)


class ConsoleBackendTests(TestCase):
    """Tests for ConsoleBackend."""

    def test_send_returns_success(self) -> None:
        """Should return successful result."""
        backend = ConsoleBackend()

        result = backend.send(
            event="order.confirmed",
            recipient="test@example.com",
            context={"order_ref": "ORD-123"},
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.message_id)

    def test_send_logs_notification(self) -> None:
        """Should log notification via logger.info."""
        backend = ConsoleBackend()

        # ConsoleBackend uses logger.info, not stdout
        with patch(
            "shopman.notifications.backends.console.logger"
        ) as mock_logger:
            backend.send(
                event="order.shipped",
                recipient="customer@example.com",
                context={"tracking": "ABC123"},
            )

            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args[0][0]
            self.assertIn("order.shipped", call_args)
            self.assertIn("customer@example.com", call_args)

    def test_send_generates_consistent_message_id_per_instance(self) -> None:
        """Should generate message ID based on instance id."""
        backend = ConsoleBackend()

        # Same instance = same id (by design, uses id(self))
        result1 = backend.send(event="e1", recipient="r1", context={})
        result2 = backend.send(event="e2", recipient="r2", context={})
        self.assertEqual(result1.message_id, result2.message_id)

        # Different instances = different ids
        backend2 = ConsoleBackend()
        result3 = backend2.send(event="e3", recipient="r3", context={})
        self.assertNotEqual(result1.message_id, result3.message_id)


class WebhookBackendTests(TestCase):
    """Tests for WebhookBackend."""

    def test_init_with_defaults(self) -> None:
        """Should initialize with default headers and timeout."""
        backend = WebhookBackend(url="https://example.com/webhook")

        self.assertEqual(backend.url, "https://example.com/webhook")
        self.assertEqual(backend.headers, {})
        self.assertEqual(backend.timeout, 10)

    def test_init_with_custom_headers(self) -> None:
        """Should accept custom headers and timeout."""
        backend = WebhookBackend(
            url="https://example.com/webhook",
            headers={"Authorization": "Bearer token"},
            timeout=30,
        )

        self.assertEqual(backend.headers, {"Authorization": "Bearer token"})
        self.assertEqual(backend.timeout, 30)

    @patch("shopman.notifications.backends.webhook.urlopen")
    def test_send_success(self, mock_urlopen) -> None:
        """Should return success when webhook call succeeds."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        backend = WebhookBackend(url="https://example.com/hook")
        result = backend.send(
            event="order.created",
            recipient="user@example.com",
            context={"order_ref": "ORD-123"},
        )

        self.assertTrue(result.success)
        self.assertEqual(result.message_id, "webhook_200")
        mock_urlopen.assert_called_once()

    @patch("shopman.notifications.backends.webhook.urlopen")
    def test_send_http_error(self, mock_urlopen) -> None:
        """Should handle HTTP errors gracefully."""
        mock_urlopen.side_effect = HTTPError(
            url="https://example.com",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=None,
        )

        backend = WebhookBackend(url="https://example.com/hook")
        result = backend.send(event="test", recipient="test", context={})

        self.assertFalse(result.success)
        self.assertIn("500", result.error)

    @patch("shopman.notifications.backends.webhook.urlopen")
    def test_send_url_error(self, mock_urlopen) -> None:
        """Should handle URL errors (network issues)."""
        mock_urlopen.side_effect = URLError("Connection refused")

        backend = WebhookBackend(url="https://example.com/hook")
        result = backend.send(event="test", recipient="test", context={})

        self.assertFalse(result.success)
        self.assertIn("Connection refused", result.error)

    @patch("shopman.notifications.backends.webhook.urlopen")
    def test_send_unexpected_error(self, mock_urlopen) -> None:
        """Should handle unexpected exceptions."""
        mock_urlopen.side_effect = RuntimeError("Unexpected error")

        backend = WebhookBackend(url="https://example.com/hook")
        result = backend.send(event="test", recipient="test", context={})

        self.assertFalse(result.success)
        self.assertIn("Unexpected error", result.error)


class EmailBackendTests(TestCase):
    """Tests for EmailBackend."""

    def test_init_with_defaults(self) -> None:
        """Should initialize with default values."""
        backend = EmailBackend()

        self.assertIsNotNone(backend.from_email)
        self.assertEqual(backend.subject_prefix, "")

    def test_init_with_custom_values(self) -> None:
        """Should accept custom from_email and prefix."""
        backend = EmailBackend(
            from_email="custom@example.com",
            subject_prefix="[Test]",
        )

        self.assertEqual(backend.from_email, "custom@example.com")
        self.assertEqual(backend.subject_prefix, "[Test]")

    @patch("shopman.notifications.backends.email.send_mail")
    def test_send_success(self, mock_send_mail) -> None:
        """Should return success when email is sent."""
        mock_send_mail.return_value = 1

        backend = EmailBackend()
        result = backend.send(
            event="order.confirmed",
            recipient="customer@example.com",
            context={"order_ref": "ORD-123"},
        )

        self.assertTrue(result.success)
        self.assertEqual(result.message_id, "email_customer@example.com")
        mock_send_mail.assert_called_once()

    @patch("shopman.notifications.backends.email.send_mail")
    def test_send_handles_exception(self, mock_send_mail) -> None:
        """Should return error when send_mail fails."""
        mock_send_mail.side_effect = Exception("SMTP connection failed")

        backend = EmailBackend()
        result = backend.send(
            event="order.confirmed",
            recipient="customer@example.com",
            context={},
        )

        self.assertFalse(result.success)
        self.assertIn("SMTP connection failed", result.error)

    def test_build_subject_with_template(self) -> None:
        """Should use template for known events."""
        backend = EmailBackend()

        subject = backend._build_subject(
            "order.confirmed",
            {"order_ref": "ORD-123"},
        )

        self.assertIn("ORD-123", subject)
        self.assertIn("confirmado", subject)

    def test_build_subject_with_prefix(self) -> None:
        """Should add prefix to subject."""
        backend = EmailBackend(subject_prefix="[Loja]")

        subject = backend._build_subject(
            "order.confirmed",
            {"order_ref": "ORD-123"},
        )

        self.assertTrue(subject.startswith("[Loja]"))

    def test_build_subject_fallback_for_unknown_event(self) -> None:
        """Should use fallback for unknown events."""
        backend = EmailBackend()

        subject = backend._build_subject(
            "unknown.event",
            {},
        )

        self.assertIn("unknown.event", subject)

    def test_build_subject_handles_missing_context_vars(self) -> None:
        """Should handle missing context variables gracefully."""
        backend = EmailBackend()

        # order_ref is required in template but not provided
        subject = backend._build_subject(
            "order.confirmed",
            {},  # Missing order_ref
        )

        # Should use template as-is when format fails
        self.assertIn("order_ref", subject)

    def test_build_body_with_customer_name(self) -> None:
        """Should include customer name greeting."""
        backend = EmailBackend()

        body = backend._build_body(
            "order.confirmed",
            {"order_ref": "ORD-123", "customer_name": "João", "total": "R$ 100,00"},
        )

        self.assertIn("João", body)

    def test_build_body_without_customer_name(self) -> None:
        """Should work without customer name."""
        backend = EmailBackend()

        body = backend._build_body(
            "order.confirmed",
            {"order_ref": "ORD-123", "total": "R$ 100,00"},
        )

        self.assertIn("ORD-123", body)

    def test_build_body_fallback_for_unknown_event(self) -> None:
        """Should use fallback body for unknown events."""
        backend = EmailBackend()

        body = backend._build_body(
            "unknown.event",
            {"order_ref": "ORD-456"},
        )

        self.assertIn("unknown.event", body)
        self.assertIn("ORD-456", body)

    def test_build_body_handles_missing_context_vars(self) -> None:
        """Should use fallback when template format fails."""
        backend = EmailBackend()

        body = backend._build_body(
            "order.confirmed",
            {},  # Missing all variables
        )

        # Should fall back to generic message
        self.assertIn("order.confirmed", body)


class TwilioSMSBackendTests(TestCase):
    """Tests for TwilioSMSBackend."""

    def test_init_stores_credentials(self) -> None:
        """Should store account SID, token, and from number."""
        backend = TwilioSMSBackend(
            account_sid="ACtest123",
            auth_token="secret456",
            from_number="+15551234567",
        )

        self.assertEqual(backend.account_sid, "ACtest123")
        self.assertEqual(backend.auth_token, "secret456")
        self.assertEqual(backend.from_number, "+15551234567")
        self.assertIn("ACtest123", backend.url)

    @patch("shopman.notifications.backends.sms.urlopen")
    def test_send_success(self, mock_urlopen) -> None:
        """Should return success when Twilio call succeeds."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"sid": "SM123"}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        backend = TwilioSMSBackend(
            account_sid="ACtest",
            auth_token="token",
            from_number="+15551234567",
        )
        result = backend.send(
            event="order.confirmed",
            recipient="+5511999999999",
            context={"order_ref": "ORD-123", "total": "R$ 100,00"},
        )

        self.assertTrue(result.success)
        self.assertEqual(result.message_id, "SM123")

    @patch("shopman.notifications.backends.sms.urlopen")
    def test_send_http_error(self, mock_urlopen) -> None:
        """Should handle Twilio HTTP errors."""
        mock_error = HTTPError(
            url="https://api.twilio.com",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=MagicMock(read=MagicMock(return_value=b'{"error": "Invalid number"}')),
        )
        mock_urlopen.side_effect = mock_error

        backend = TwilioSMSBackend(
            account_sid="ACtest",
            auth_token="token",
            from_number="+15551234567",
        )
        result = backend.send(
            event="test",
            recipient="+invalid",
            context={},
        )

        self.assertFalse(result.success)
        self.assertIn("400", result.error)

    @patch("shopman.notifications.backends.sms.urlopen")
    def test_send_exception(self, mock_urlopen) -> None:
        """Should handle unexpected errors."""
        mock_urlopen.side_effect = Exception("Network error")

        backend = TwilioSMSBackend(
            account_sid="ACtest",
            auth_token="token",
            from_number="+15551234567",
        )
        result = backend.send(
            event="test",
            recipient="+5511999999999",
            context={},
        )

        self.assertFalse(result.success)
        self.assertIn("Network error", result.error)

    def test_build_message_with_template(self) -> None:
        """Should use template for known events."""
        backend = TwilioSMSBackend(
            account_sid="ACtest",
            auth_token="token",
            from_number="+1555",
        )

        message = backend._build_message(
            "order.confirmed",
            {"order_ref": "ORD-123", "total": "R$ 50,00"},
        )

        self.assertIn("ORD-123", message)
        self.assertIn("R$ 50,00", message)

    def test_build_message_fallback(self) -> None:
        """Should use fallback for unknown events."""
        backend = TwilioSMSBackend(
            account_sid="ACtest",
            auth_token="token",
            from_number="+1555",
        )

        message = backend._build_message(
            "unknown.event",
            {"order_ref": "ORD-456"},
        )

        self.assertIn("unknown.event", message)
        self.assertIn("ORD-456", message)

    def test_build_message_missing_vars(self) -> None:
        """Should fallback when template format fails."""
        backend = TwilioSMSBackend(
            account_sid="ACtest",
            auth_token="token",
            from_number="+1555",
        )

        message = backend._build_message(
            "order.confirmed",
            {},  # Missing variables
        )

        self.assertIn("Shopman", message)


class WhatsAppBackendTests(TestCase):
    """Tests for WhatsAppBackend."""

    def test_init_stores_credentials(self) -> None:
        """Should store credentials and build URL."""
        backend = WhatsAppBackend(
            phone_number_id="123456",
            access_token="EAAtoken",
            api_version="v18.0",
        )

        self.assertEqual(backend.phone_number_id, "123456")
        self.assertEqual(backend.access_token, "EAAtoken")
        self.assertEqual(backend.api_version, "v18.0")
        self.assertIn("123456", backend.url)
        self.assertIn("v18.0", backend.url)

    @patch("shopman.notifications.backends.whatsapp.urlopen")
    def test_send_success(self, mock_urlopen) -> None:
        """Should return success when Meta API call succeeds."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"messages": [{"id": "wamid.123"}]}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        backend = WhatsAppBackend(
            phone_number_id="123456",
            access_token="token",
        )
        result = backend.send(
            event="order.confirmed",
            recipient="+5511999999999",
            context={"order_ref": "ORD-123"},
        )

        self.assertTrue(result.success)
        self.assertEqual(result.message_id, "wamid.123")

    @patch("shopman.notifications.backends.whatsapp.urlopen")
    def test_send_http_error(self, mock_urlopen) -> None:
        """Should handle Meta API HTTP errors."""
        mock_error = HTTPError(
            url="https://graph.facebook.com",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=MagicMock(read=MagicMock(return_value=b'{"error": {"message": "Invalid template"}}')),
        )
        mock_urlopen.side_effect = mock_error

        backend = WhatsAppBackend(
            phone_number_id="123456",
            access_token="token",
        )
        result = backend.send(
            event="test",
            recipient="+5511999999999",
            context={},
        )

        self.assertFalse(result.success)
        self.assertIn("400", result.error)

    @patch("shopman.notifications.backends.whatsapp.urlopen")
    def test_send_exception(self, mock_urlopen) -> None:
        """Should handle unexpected errors."""
        mock_urlopen.side_effect = Exception("Network timeout")

        backend = WhatsAppBackend(
            phone_number_id="123456",
            access_token="token",
        )
        result = backend.send(
            event="test",
            recipient="+5511999999999",
            context={},
        )

        self.assertFalse(result.success)
        self.assertIn("Network timeout", result.error)

    def test_get_template_name(self) -> None:
        """Should convert event name to template name."""
        backend = WhatsAppBackend(phone_number_id="123", access_token="token")

        name = backend._get_template_name("order.confirmed")
        self.assertEqual(name, "order_confirmed")

        name = backend._get_template_name("status.updated")
        self.assertEqual(name, "status_updated")

    def test_build_components_with_params(self) -> None:
        """Should build components from context."""
        backend = WhatsAppBackend(phone_number_id="123", access_token="token")

        components = backend._build_components({
            "order_ref": "ORD-123",
            "customer_name": "João",
            "total": "R$ 100,00",
        })

        self.assertEqual(len(components), 1)
        self.assertEqual(components[0]["type"], "body")
        self.assertEqual(len(components[0]["parameters"]), 3)

    def test_build_components_empty(self) -> None:
        """Should return empty list when no params."""
        backend = WhatsAppBackend(phone_number_id="123", access_token="token")

        components = backend._build_components({
            "unknown_key": "value",
        })

        self.assertEqual(components, [])
