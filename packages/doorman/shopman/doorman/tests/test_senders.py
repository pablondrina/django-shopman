"""
Tests for Auth message senders.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from shopman.doorman.senders import (
    ConsoleSender,
    EmailSender,
    LogSender,
    SMSSender,
    WhatsAppCloudAPISender,
)


class TestConsoleSender:
    """Tests for ConsoleSender (development)."""

    def test_send_code_returns_true(self):
        sender = ConsoleSender()
        assert sender.send_code("+5541999999999", "123456", "whatsapp") is True

    def test_send_code_prints_to_stdout(self, capsys):
        sender = ConsoleSender()
        sender.send_code("+5541999999999", "123456", "whatsapp")
        output = capsys.readouterr().out
        assert "123456" in output
        assert "+5541999999999" in output
        assert "whatsapp" in output


class TestLogSender:
    """Tests for LogSender (testing)."""

    def test_send_code_returns_true(self):
        sender = LogSender()
        assert sender.send_code("+5541999999999", "654321", "sms") is True

    def test_send_code_logs_message(self, caplog):
        sender = LogSender()
        with caplog.at_level(logging.INFO, logger="shopman.doorman.senders"):
            sender.send_code("+5541999999999", "654321", "sms")
        assert "+5541999999999" in caplog.text


class TestSMSSender:
    """Tests for SMSSender (stub)."""

    def test_send_code_returns_false(self):
        sender = SMSSender()
        assert sender.send_code("+5541999999999", "123456", "sms") is False

    def test_send_code_does_not_log_raw_code(self, caplog):
        """SMSSender must NOT leak the raw OTP code in logs."""
        sender = SMSSender()
        with caplog.at_level(logging.WARNING, logger="shopman.doorman.senders"):
            sender.send_code("+5541999999999", "SECRET_CODE_987654", "sms")
        assert "SECRET_CODE_987654" not in caplog.text

    def test_send_code_logs_warning(self, caplog):
        sender = SMSSender()
        with caplog.at_level(logging.WARNING, logger="shopman.doorman.senders"):
            sender.send_code("+5541999999999", "123456", "sms")
        assert "not implemented" in caplog.text


class TestEmailSender:
    """Tests for EmailSender (Django email backend)."""

    @pytest.mark.django_db
    def test_send_code_sends_email(self):
        sender = EmailSender()
        with patch("django.core.mail.EmailMultiAlternatives") as MockEmail:
            mock_msg = MagicMock()
            MockEmail.return_value = mock_msg

            with patch("django.template.loader.render_to_string", return_value="body"):
                result = sender.send_code("user@example.com", "123456", "email")

        assert result is True
        mock_msg.attach_alternative.assert_called_once()
        mock_msg.send.assert_called_once_with(fail_silently=False)

    @pytest.mark.django_db
    def test_send_code_handles_exception(self):
        sender = EmailSender()
        with patch(
            "django.template.loader.render_to_string",
            side_effect=Exception("SMTP down"),
        ):
            result = sender.send_code("user@example.com", "123456", "email")
        assert result is False


class TestWhatsAppCloudAPISender:
    """Tests for WhatsAppCloudAPISender.

    Requires httpx (optional dependency). WhatsApp OTP delivery in production
    uses ManyChat, not the Meta Cloud API directly. This sender exists as a
    fallback option but is not actively used. Tests are skipped when httpx
    is not installed.
    """

    httpx = pytest.importorskip("httpx")

    @override_settings(DOORMAN={
        "WHATSAPP_ACCESS_TOKEN": "test-token",
        "WHATSAPP_PHONE_ID": "12345",
        "WHATSAPP_CODE_TEMPLATE": "verification_code",
    })
    def test_send_code_success(self):
        sender = WhatsAppCloudAPISender()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response) as mock_post:
            result = sender.send_code("+5541999999999", "123456", "whatsapp")

        assert result is True
        mock_post.assert_called_once()
        # Verify phone is sent without + prefix
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["json"]["to"] == "5541999999999"

    @override_settings(DOORMAN={
        "WHATSAPP_ACCESS_TOKEN": "test-token",
        "WHATSAPP_PHONE_ID": "12345",
        "WHATSAPP_CODE_TEMPLATE": "verification_code",
    })
    def test_send_code_api_failure(self):
        sender = WhatsAppCloudAPISender()
        with patch("httpx.post", side_effect=Exception("Timeout")):
            result = sender.send_code("+5541999999999", "123456", "whatsapp")
        assert result is False

    @override_settings(DOORMAN={
        "WHATSAPP_ACCESS_TOKEN": "",
        "WHATSAPP_PHONE_ID": "",
        "WHATSAPP_CODE_TEMPLATE": "",
    })
    def test_send_code_not_configured(self):
        sender = WhatsAppCloudAPISender()
        result = sender.send_code("+5541999999999", "123456", "whatsapp")
        assert result is False
