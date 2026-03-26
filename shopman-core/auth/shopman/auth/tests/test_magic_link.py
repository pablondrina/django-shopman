"""
Tests for access link email login via AccessLinkService.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory, override_settings

from shopman.auth.services.access_link import AccessLinkService
from shopman.auth.views.access_link_request import AccessLinkRequestView


@pytest.mark.django_db
class TestAccessLinkEmailService:
    """Tests for AccessLinkService access link email methods."""

    @patch("shopman.auth.services.access_link.AccessLinkService._send_access_link_email")
    def test_send_access_link_success(self, mock_send, customer):
        """Access link should be sent for existing customer with email."""
        mock_send.return_value = True
        result = AccessLinkService.send_access_link(customer.email)
        assert result.success

    @patch("shopman.auth.services.access_link.AccessLinkService._send_access_link_email")
    def test_send_access_link_email_not_found(self, mock_send):
        """Unknown email should return error."""
        result = AccessLinkService.send_access_link("unknown@example.com")
        assert not result.success
        mock_send.assert_not_called()

    def test_send_access_link_invalid_email(self):
        """Invalid email should return error."""
        result = AccessLinkService.send_access_link("not-an-email")
        assert not result.success

    def test_send_access_link_empty_email(self):
        """Empty email should return error."""
        result = AccessLinkService.send_access_link("")
        assert not result.success

    @override_settings(AUTH={"ACCESS_LINK_ENABLED": False})
    def test_send_access_link_disabled(self):
        """When disabled, should return error."""
        result = AccessLinkService.send_access_link("test@example.com")
        assert not result.success
        assert "disabled" in result.error.lower()

    @patch("shopman.auth.services.access_link.AccessLinkService._send_access_link_email")
    def test_send_access_link_customer_inactive(self, mock_send, customer):
        """Inactive customer should return error."""
        from shopman.auth.protocols.customer import AuthCustomerInfo

        inactive = AuthCustomerInfo(
            uuid=customer.uuid, name="Inactive", phone=None,
            email=customer.email, is_active=False,
        )
        with patch("shopman.auth.services.access_link.get_adapter") as mock_get:
            mock_get.return_value.resolve_customer_by_email.return_value = inactive
            mock_get.return_value.should_auto_create_customer.return_value = True
            result = AccessLinkService.send_access_link(customer.email)
        assert not result.success
        assert "inactive" in result.error.lower()
        mock_send.assert_not_called()

    @patch("shopman.auth.services.access_link.AccessLinkService._send_access_link_email")
    def test_send_access_link_email_send_failure(self, mock_send, customer):
        """Email send failure should return error."""
        mock_send.return_value = False
        result = AccessLinkService.send_access_link(customer.email)
        assert not result.success
        assert "send" in result.error.lower()

    @patch("shopman.auth.services.access_link.AccessLinkService._send_access_link_email")
    def test_send_access_link_rate_limited(self, mock_send, customer):
        """Should be rate-limited after too many requests to same email."""
        mock_send.return_value = True
        email = customer.email

        # Send 5 access links (within default limit)
        for _ in range(5):
            AccessLinkService.send_access_link(email)

        # 6th should be rate-limited
        result = AccessLinkService.send_access_link(email)
        assert not result.success
        assert "wait" in result.error.lower()

    def test_send_access_link_email_rendering(self):
        """_send_access_link_email should render Django templates."""
        with patch("django.core.mail.EmailMultiAlternatives") as MockEmail:
            mock_msg = MagicMock()
            MockEmail.return_value = mock_msg

            with patch("django.template.loader.render_to_string", return_value="body"):
                sent = AccessLinkService._send_access_link_email(
                    "test@example.com", "https://example.com/link", 15
                )
        assert sent is True
        mock_msg.send.assert_called_once()

    def test_send_access_link_email_failure_returns_false(self):
        """_send_access_link_email should return False on exception."""
        with patch(
            "django.template.loader.render_to_string",
            side_effect=Exception("Template error"),
        ):
            sent = AccessLinkService._send_access_link_email(
                "test@example.com", "https://example.com", 15
            )
        assert sent is False


@pytest.mark.django_db
class TestAccessLinkRequestView:
    """Tests for AccessLinkRequestView."""

    def test_get_renders_form(self):
        factory = RequestFactory()
        request = factory.get("/auth/access-link/")
        from django.contrib.sessions.backends.db import SessionStore

        request.session = SessionStore()
        response = AccessLinkRequestView.as_view()(request)
        assert response.status_code == 200

    def test_post_empty_email_returns_error(self):
        factory = RequestFactory()
        request = factory.post(
            "/auth/access-link/",
            json.dumps({"email": ""}),
            content_type="application/json",
        )
        from django.contrib.sessions.backends.db import SessionStore

        request.session = SessionStore()
        response = AccessLinkRequestView.as_view()(request)
        assert response.status_code == 400

    @override_settings(AUTH={"ACCESS_LINK_ENABLED": False})
    def test_post_disabled_returns_error(self):
        factory = RequestFactory()
        request = factory.post(
            "/auth/access-link/",
            json.dumps({"email": "test@example.com"}),
            content_type="application/json",
        )
        from django.contrib.sessions.backends.db import SessionStore

        request.session = SessionStore()
        response = AccessLinkRequestView.as_view()(request)
        assert response.status_code == 400
