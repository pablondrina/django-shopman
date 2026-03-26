"""Tests for storefront auth views: CustomerLookupView, RequestCodeView, VerifyCodeView.

WP-B5: AccessLink login, DeviceTrust, session-based auth, rate limiting.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone
from shopman.auth.models import AccessLink
from shopman.auth.models.device_trust import TrustedDevice
from shopman.customers.models import Customer

from channels.web.views.auth import (
    SESSION_CUSTOMER_UUID,
    SESSION_VERIFIED,
    SESSION_VERIFIED_PHONE,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear Django cache before each test to reset rate limits."""
    cache.clear()
    yield
    cache.clear()


# ── CustomerLookupView ────────────────────────────────────────────────


class TestCustomerLookupView:
    def test_lookup_no_phone(self, client: Client):
        resp = client.get("/checkout/customer-lookup/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is False

    def test_lookup_invalid_phone(self, client: Client):
        resp = client.get("/checkout/customer-lookup/?phone=bad")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is False

    def test_lookup_not_found(self, client: Client):
        resp = client.get("/checkout/customer-lookup/?phone=43999998888")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is False

    def test_lookup_found_no_pii(self, client: Client, customer):
        """Found customer without verified session — no PII exposed."""
        resp = client.get(f"/checkout/customer-lookup/?phone={customer.phone}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["name"] == ""  # No PII without verification
        assert data["addresses"] == []
        assert data["can_verify"] is True

    def test_lookup_verified_returns_pii(self, client: Client, customer, customer_address):
        """Verified session — returns name and addresses."""
        session = client.session
        session[SESSION_VERIFIED_PHONE] = customer.phone
        session.save()
        resp = client.get(f"/checkout/customer-lookup/?phone={customer.phone}")
        data = resp.json()
        assert data["found"] is True
        assert data["is_verified"] is True
        assert data["name"] == "João Silva"
        assert len(data["addresses"]) == 1
        assert data["addresses"][0]["is_default"] is True


# ── RequestCodeView ───────────────────────────────────────────────────


class TestRequestCodeView:
    def test_request_code_no_phone(self, client: Client):
        resp = client.post("/checkout/request-code/", {"phone": ""})
        assert resp.status_code == 200

    def test_request_code_requires_post(self, client: Client):
        resp = client.get("/checkout/request-code/")
        assert resp.status_code == 405


# ── VerifyCodeView ────────────────────────────────────────────────────


class TestVerifyCodeView:
    def test_verify_code_no_data(self, client: Client):
        resp = client.post("/checkout/verify-code/", {})
        assert resp.status_code == 200

    def test_verify_code_requires_post(self, client: Client):
        resp = client.get("/checkout/verify-code/")
        assert resp.status_code == 405


# ══════════════════════════════════════════════════════════════════════
# WP-B5: Auth Completo no Storefront
# ══════════════════════════════════════════════════════════════════════


# ── AccessLink ────────────────────────────────────────────────────


class TestAccessLinkLoginView:
    """BridgeLoginView: consume access link → authenticated session."""

    def test_access_link_creates_authenticated_session(self, client: Client, customer):
        """Valid access link creates session with customer_uuid and verified flag."""
        token = AccessLink.objects.create(
            customer_id=customer.uuid,
            audience=AccessLink.Audience.WEB_GENERAL,
            source=AccessLink.Source.INTERNAL,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        response = client.get(f"/auth/bridge/{token.token}/")

        assert response.status_code == 302
        session = client.session
        assert session[SESSION_CUSTOMER_UUID] == str(customer.uuid)
        assert session[SESSION_VERIFIED] is True
        assert session[SESSION_VERIFIED_PHONE] == customer.phone

    def test_access_link_expired_returns_error(self, client: Client, customer):
        """Expired access link renders error page."""
        token = AccessLink.objects.create(
            customer_id=customer.uuid,
            audience=AccessLink.Audience.WEB_GENERAL,
            source=AccessLink.Source.INTERNAL,
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        response = client.get(f"/auth/bridge/{token.token}/")

        assert response.status_code == 200
        assert SESSION_CUSTOMER_UUID not in client.session

    def test_access_link_invalid_returns_error(self, client: Client):
        """Non-existent access link renders error."""
        response = client.get("/auth/bridge/nonexistent-token/")

        assert response.status_code == 200
        assert SESSION_CUSTOMER_UUID not in client.session

    def test_access_link_used_returns_error(self, client: Client, customer):
        """Already-used access link returns error (outside reuse window)."""
        token = AccessLink.objects.create(
            customer_id=customer.uuid,
            audience=AccessLink.Audience.WEB_GENERAL,
            source=AccessLink.Source.INTERNAL,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        token.used_at = timezone.now() - timedelta(minutes=5)
        token.save()

        response = client.get(f"/auth/bridge/{token.token}/")

        assert response.status_code == 200
        assert SESSION_CUSTOMER_UUID not in client.session

    def test_access_link_redirects_to_next(self, client: Client, customer):
        """Access link respects ?next= parameter for redirect."""
        token = AccessLink.objects.create(
            customer_id=customer.uuid,
            audience=AccessLink.Audience.WEB_GENERAL,
            source=AccessLink.Source.INTERNAL,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        response = client.get(f"/auth/bridge/{token.token}/?next=/minha-conta/")

        assert response.status_code == 302
        assert response.url == "/minha-conta/"


# ── DeviceTrust ────────────────────────────────────────────────────


class TestDeviceTrust:
    """DeviceTrust: skip-OTP on revisits."""

    def test_device_trust_skips_otp(self, client: Client, customer):
        """Trusted device allows auto-login without OTP."""
        device, raw_token = TrustedDevice.create_for_customer(
            customer_id=customer.uuid,
            user_agent="Mozilla/5.0 Test",
            ip_address="127.0.0.1",
        )

        from shopman.auth.conf import auth_settings

        client.cookies[auth_settings.DEVICE_TRUST_COOKIE_NAME] = raw_token

        response = client.post("/auth/device-check/", {"phone": customer.phone})

        assert response.status_code == 200
        data = response.json()
        assert data["trusted"] is True
        assert data["name"] == customer.name

        session = client.session
        assert session[SESSION_CUSTOMER_UUID] == str(customer.uuid)
        assert session[SESSION_VERIFIED] is True

    def test_device_trust_expired_requires_otp(self, client: Client, customer):
        """Expired device trust does NOT auto-login."""
        device, raw_token = TrustedDevice.create_for_customer(
            customer_id=customer.uuid,
            user_agent="Mozilla/5.0 Test",
            ip_address="127.0.0.1",
        )
        device.expires_at = timezone.now() - timedelta(days=1)
        device.save()

        from shopman.auth.conf import auth_settings

        client.cookies[auth_settings.DEVICE_TRUST_COOKIE_NAME] = raw_token

        response = client.post("/auth/device-check/", {"phone": customer.phone})

        data = response.json()
        assert data["trusted"] is False
        assert SESSION_CUSTOMER_UUID not in client.session

    def test_device_trust_wrong_customer(self, client: Client, customer):
        """Device trusted for one customer cannot login as another."""
        other = Customer.objects.create(
            ref="AUTH-OTHER", first_name="Pedro", last_name="Lima", phone="5543999880099",
        )

        device, raw_token = TrustedDevice.create_for_customer(
            customer_id=other.uuid,
            user_agent="Mozilla/5.0 Test",
            ip_address="127.0.0.1",
        )

        from shopman.auth.conf import auth_settings

        client.cookies[auth_settings.DEVICE_TRUST_COOKIE_NAME] = raw_token

        response = client.post("/auth/device-check/", {"phone": customer.phone})

        data = response.json()
        assert data["trusted"] is False

    def test_verify_code_sets_device_trust_cookie(self, client: Client, customer):
        """Successful OTP verification sets device trust cookie on response."""
        with patch("shopman.auth.services.verification.AuthService") as mock_vs:
            from shopman.auth.protocols.customer import AuthCustomerInfo

            mock_customer = AuthCustomerInfo(
                uuid=customer.uuid,
                name=customer.name,
                phone=customer.phone,
                email="",
                is_active=True,
            )
            mock_vs.verify_for_login.return_value = type("R", (), {
                "success": True, "customer": mock_customer,
                "created_customer": False, "error": None, "attempts_remaining": None,
            })()

            response = client.post("/checkout/verify-code/", {
                "phone": customer.phone, "code": "123456",
            })

            assert response.status_code == 200
            from shopman.auth.conf import auth_settings

            cookie_name = auth_settings.DEVICE_TRUST_COOKIE_NAME
            assert cookie_name in response.cookies


# ── Rate Limiting ──────────────────────────────────────────────────


class TestRateLimiting:
    """Rate limiting on auth endpoints."""

    def test_rate_limit_blocks_excessive_code_requests(self, client: Client, customer):
        """RequestCodeView blocks after 3 requests in 10 min window."""
        phone = customer.phone

        with patch("shopman.auth.services.verification.AuthService") as mock_vs:
            mock_vs.request_code.return_value = type("R", (), {
                "success": True, "code_id": "x", "expires_at": "x",
            })()

            for _ in range(3):
                client.post("/checkout/request-code/", {"phone": phone})

            mock_vs.request_code.reset_mock()
            response = client.post("/checkout/request-code/", {"phone": phone})

            assert response.status_code == 200
            assert "Muitas tentativas" in response.content.decode()

    def test_rate_limit_blocks_excessive_verify_attempts(self, client: Client, customer):
        """VerifyCodeView blocks after 5 attempts in 10 min window."""
        phone = customer.phone

        with patch("shopman.auth.services.verification.AuthService") as mock_vs:
            mock_vs.verify_for_login.return_value = type("R", (), {
                "success": False, "error": "Incorrect code.",
                "attempts_remaining": 4, "customer": None,
            })()

            for _ in range(5):
                client.post("/checkout/verify-code/", {"phone": phone, "code": "000000"})

            mock_vs.verify_for_login.reset_mock()
            response = client.post("/checkout/verify-code/", {"phone": phone, "code": "000000"})

            assert response.status_code == 200
            assert "Muitas tentativas" in response.content.decode()


# ── Session Auth ───────────────────────────────────────────────────


class TestSessionAuth:
    """Session-based auth protects account views."""

    def test_session_auth_protects_account_views(self, client: Client, customer):
        """AccountView shows customer data only when session is authenticated."""
        # No session → empty account page
        response = client.get("/minha-conta/")
        assert response.status_code == 200
        assert response.context["customer"] is None

        # Set session auth
        session = client.session
        session[SESSION_CUSTOMER_UUID] = str(customer.uuid)
        session[SESSION_VERIFIED] = True
        session[SESSION_VERIFIED_PHONE] = customer.phone
        session.save()

        response = client.get("/minha-conta/")
        assert response.status_code == 200
        assert response.context["customer"] is not None
        assert response.context["customer"].pk == customer.pk
        assert response.context["is_verified"] is True

    def test_session_auth_invalid_uuid_shows_empty(self, client: Client):
        """Invalid customer UUID in session shows empty account."""
        session = client.session
        session[SESSION_CUSTOMER_UUID] = "00000000-0000-0000-0000-000000000000"
        session[SESSION_VERIFIED] = True
        session.save()

        response = client.get("/minha-conta/")
        assert response.status_code == 200
        assert response.context["customer"] is None

    def test_session_without_verified_flag_shows_empty(self, client: Client, customer):
        """customer_uuid in session without verified=True is not authenticated."""
        session = client.session
        session[SESSION_CUSTOMER_UUID] = str(customer.uuid)
        # SESSION_VERIFIED not set
        session.save()

        response = client.get("/minha-conta/")
        assert response.status_code == 200
        assert response.context["customer"] is None

    def test_verify_code_sets_session_auth(self, client: Client, customer):
        """Successful OTP verification sets full session auth vars."""
        with patch("shopman.auth.services.verification.AuthService") as mock_vs:
            from shopman.auth.protocols.customer import AuthCustomerInfo

            mock_customer = AuthCustomerInfo(
                uuid=customer.uuid,
                name=customer.name,
                phone=customer.phone,
                email="",
                is_active=True,
            )
            mock_vs.verify_for_login.return_value = type("R", (), {
                "success": True, "customer": mock_customer,
                "created_customer": False, "error": None, "attempts_remaining": None,
            })()

            response = client.post("/checkout/verify-code/", {
                "phone": customer.phone, "code": "123456",
            })

            assert response.status_code == 200
            session = client.session
            assert session[SESSION_CUSTOMER_UUID] == str(customer.uuid)
            assert session[SESSION_VERIFIED] is True
            assert session[SESSION_VERIFIED_PHONE] == customer.phone


# ── Account OTP Gate ──────────────────────────────────────────────────


class TestAccountOTPGate:
    """Account page requires OTP verification — phone alone must NOT expose data."""

    def test_account_post_without_otp_does_not_show_data(self, client: Client, customer):
        """POST with valid phone but no OTP must NOT return customer data."""
        response = client.post("/minha-conta/", {"phone": customer.phone})
        assert response.status_code == 200
        # Must NOT have customer object in context
        assert response.context["customer"] is None
        # Must show verification prompt
        assert response.context.get("needs_verification") is True

    def test_account_post_shows_verification_prompt(self, client: Client, customer):
        """POST with valid phone shows OTP request form, not account data."""
        response = client.post("/minha-conta/", {"phone": customer.phone})
        content = response.content.decode()
        assert "Confirme sua identidade" in content
        # Must NOT contain sensitive data
        assert customer.phone not in content or "needs_verification" in str(response.context)
        # Must NOT contain address or order data
        assert "Enderecos" not in content
        assert "Ultimos pedidos" not in content

    def test_account_get_shows_data_when_verified(self, client: Client, customer):
        """GET with verified session shows full account data."""
        session = client.session
        session[SESSION_CUSTOMER_UUID] = str(customer.uuid)
        session[SESSION_VERIFIED] = True
        session[SESSION_VERIFIED_PHONE] = customer.phone
        session.save()

        response = client.get("/minha-conta/")
        assert response.status_code == 200
        assert response.context["customer"] is not None
        assert response.context["customer"].pk == customer.pk

    def test_account_post_with_verified_session_shows_data(self, client: Client, customer):
        """POST with valid phone AND verified session shows data directly."""
        session = client.session
        session[SESSION_CUSTOMER_UUID] = str(customer.uuid)
        session[SESSION_VERIFIED] = True
        session[SESSION_VERIFIED_PHONE] = customer.phone
        session.save()

        response = client.post("/minha-conta/", {"phone": customer.phone})
        assert response.status_code == 200
        assert response.context["customer"] is not None


# ── Address Auth ──────────────────────────────────────────────────────


class TestAddressAuth:
    """Address CRUD requires session auth — no phone fallback."""

    def test_address_create_requires_session_auth(self, client: Client, customer):
        """POST to create address without session auth returns 401."""
        response = client.post("/minha-conta/enderecos/", {
            "formatted_address": "Rua Nova 456",
            "label": "work",
        })
        assert response.status_code == 401

    def test_address_update_requires_session_auth(self, client: Client, customer_address):
        """POST to update address without session auth returns 401."""
        response = client.post(f"/minha-conta/enderecos/{customer_address.pk}/", {
            "formatted_address": "Rua Alterada 789",
        })
        assert response.status_code == 401

    def test_address_delete_requires_session_auth(self, client: Client, customer_address):
        """POST to delete address without session auth returns 401."""
        response = client.post(f"/minha-conta/enderecos/{customer_address.pk}/delete/")
        assert response.status_code == 401

    def test_address_set_default_requires_session_auth(self, client: Client, customer_address):
        """POST to set default address without session auth returns 401."""
        response = client.post(f"/minha-conta/enderecos/{customer_address.pk}/default/")
        assert response.status_code == 401

    def test_address_create_works_with_session_auth(self, client: Client, customer):
        """POST to create address WITH session auth succeeds."""
        session = client.session
        session[SESSION_CUSTOMER_UUID] = str(customer.uuid)
        session[SESSION_VERIFIED] = True
        session[SESSION_VERIFIED_PHONE] = customer.phone
        session.save()

        response = client.post("/minha-conta/enderecos/", {
            "formatted_address": "Rua Nova 456 - Centro - Londrina",
            "label": "work",
        })
        assert response.status_code == 200
