"""Tests for storefront auth views: CustomerLookupView, RequestCodeView, VerifyCodeView.

WP-B5: AccessLink login, DeviceTrust, session-based auth, rate limiting.
AUTH-6B: Cutover to request.customer (Django auth).
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, override_settings
from django.utils import timezone
from shopman.doorman import TrustedDevice
from shopman.doorman.models import AccessLink
from shopman.guestman.models import Customer

pytestmark = pytest.mark.django_db


def _login_as_customer(client: Client, customer) -> User:
    """Log in the Django test client as a customer via Django auth."""
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    info = AuthCustomerInfo(
        uuid=customer.uuid,
        name=customer.name,
        phone=customer.phone,
        email=getattr(customer, "email", None) or None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")
    return user


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
        """Found customer without auth — no PII exposed."""
        resp = client.get(f"/checkout/customer-lookup/?phone={customer.phone}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["name"] == ""  # No PII without verification
        assert data["addresses"] == []
        assert data["can_verify"] is True

    def test_lookup_verified_returns_pii(self, client: Client, customer, customer_address):
        """Authenticated user — returns name and addresses."""
        _login_as_customer(client, customer)
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
        """Valid access link logs in via Django auth."""
        link, raw_token = AccessLink.create_with_token(
            customer_id=customer.uuid,
            audience=AccessLink.Audience.WEB_GENERAL,
            source=AccessLink.Source.INTERNAL,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        response = client.get(f"/auth/access/{raw_token}/")

        assert response.status_code == 302
        # Django auth user should be set
        user_id = client.session.get("_auth_user_id")
        assert user_id is not None

    def test_access_link_expired_returns_error(self, client: Client, customer):
        """Expired access link renders error page."""
        link, raw_token = AccessLink.create_with_token(
            customer_id=customer.uuid,
            audience=AccessLink.Audience.WEB_GENERAL,
            source=AccessLink.Source.INTERNAL,
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        response = client.get(f"/auth/access/{raw_token}/")

        assert response.status_code == 200
        assert client.session.get("_auth_user_id") is None

    def test_access_link_invalid_returns_error(self, client: Client):
        """Non-existent access link renders error."""
        response = client.get("/auth/access/nonexistent-token/")

        assert response.status_code == 200
        assert client.session.get("_auth_user_id") is None

    def test_access_link_used_returns_error(self, client: Client, customer):
        """Already-used access link returns error (outside reuse window)."""
        link, raw_token = AccessLink.create_with_token(
            customer_id=customer.uuid,
            audience=AccessLink.Audience.WEB_GENERAL,
            source=AccessLink.Source.INTERNAL,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        link.used_at = timezone.now() - timedelta(minutes=5)
        link.save()

        response = client.get(f"/auth/access/{raw_token}/")

        assert response.status_code == 200
        assert client.session.get("_auth_user_id") is None

    def test_access_link_redirects_to_next(self, client: Client, customer):
        """Access link respects ?next= parameter for redirect."""
        link, raw_token = AccessLink.create_with_token(
            customer_id=customer.uuid,
            audience=AccessLink.Audience.WEB_GENERAL,
            source=AccessLink.Source.INTERNAL,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        response = client.get(f"/auth/access/{raw_token}/?next=/minha-conta/")

        assert response.status_code == 302
        assert response.url == "/minha-conta/"


# ── DeviceTrust ────────────────────────────────────────────────────


class TestDeviceTrust:
    """DeviceTrust: skip-OTP on revisits."""

    def test_device_trust_skips_otp(self, client: Client, customer):
        """Trusted device auto-logins and returns greeting HTML (no OTP needed)."""
        device, raw_token = TrustedDevice.create_for_customer(
            customer_id=customer.uuid,
            user_agent="Mozilla/5.0 Test",
            ip_address="127.0.0.1",
        )

        from shopman.doorman.conf import doorman_settings

        client.cookies[doorman_settings.DEVICE_TRUST_COOKIE_NAME] = raw_token

        response = client.post("/auth/device-check/", {"phone": customer.phone})

        assert response.status_code == 200
        content = response.content.decode()
        # Returns greeting HTML, not JSON
        assert "Bem-vindo de volta" in content

        # Django auth user should be set
        user_id = client.session.get("_auth_user_id")
        assert user_id is not None

    def test_device_trust_expired_requires_otp(self, client: Client, customer):
        """Expired device trust returns 204 (HTMX no-swap) and does NOT auto-login."""
        device, raw_token = TrustedDevice.create_for_customer(
            customer_id=customer.uuid,
            user_agent="Mozilla/5.0 Test",
            ip_address="127.0.0.1",
        )
        device.expires_at = timezone.now() - timedelta(days=1)
        device.save()

        from shopman.doorman.conf import doorman_settings

        client.cookies[doorman_settings.DEVICE_TRUST_COOKIE_NAME] = raw_token

        response = client.post("/auth/device-check/", {"phone": customer.phone})

        assert response.status_code == 204
        assert client.session.get("_auth_user_id") is None

    def test_device_trust_wrong_customer(self, client: Client, customer):
        """Device trusted for one customer returns 204 when phone doesn't match."""
        other = Customer.objects.create(
            ref="AUTH-OTHER", first_name="Pedro", last_name="Lima", phone="5543999880099",
        )

        device, raw_token = TrustedDevice.create_for_customer(
            customer_id=other.uuid,
            user_agent="Mozilla/5.0 Test",
            ip_address="127.0.0.1",
        )

        from shopman.doorman.conf import doorman_settings

        client.cookies[doorman_settings.DEVICE_TRUST_COOKIE_NAME] = raw_token

        response = client.post("/auth/device-check/", {"phone": customer.phone})

        assert response.status_code == 204

    def test_verify_code_no_longer_sets_cookie_directly(self, client: Client, customer):
        """OTP verification no longer auto-trusts — cookie deferred to TrustDeviceView."""
        with patch("shopman.doorman.services.verification.AuthService") as mock_vs:
            from shopman.doorman.protocols.customer import AuthCustomerInfo

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
            from shopman.doorman.conf import doorman_settings

            cookie_name = doorman_settings.DEVICE_TRUST_COOKIE_NAME
            # Cookie not set here anymore — user must confirm via TrustDeviceView
            assert cookie_name not in response.cookies

    def test_trust_device_view_sets_cookie(self, client: Client, customer):
        """TrustDeviceView sets device trust cookie when trust=1."""
        _login_as_customer(client, customer)
        response = client.post("/auth/trust-device/", {"trust": "1"})
        assert response.status_code == 200
        from shopman.doorman.conf import doorman_settings
        assert doorman_settings.DEVICE_TRUST_COOKIE_NAME in response.cookies

    def test_trust_device_view_no_cookie_when_skipped(self, client: Client, customer):
        """TrustDeviceView does NOT set cookie when trust=0."""
        _login_as_customer(client, customer)
        response = client.post("/auth/trust-device/", {"trust": "0"})
        assert response.status_code == 200
        from shopman.doorman.conf import doorman_settings
        assert doorman_settings.DEVICE_TRUST_COOKIE_NAME not in response.cookies


# ── Rate Limiting ──────────────────────────────────────────────────


class TestRateLimiting:
    """Rate limiting on auth endpoints using django-ratelimit."""

    @override_settings(RATELIMIT_ENABLE=True)
    def test_rate_limit_blocks_excessive_code_requests(self, client: Client, customer):
        """RequestCodeView blocks after 5 requests/min with HTTP 429."""
        phone = customer.phone

        with patch("shopman.doorman.services.verification.AuthService") as mock_vs:
            mock_vs.request_code.return_value = type("R", (), {
                "success": True, "code_id": "x", "expires_at": "x",
            })()

            for _ in range(5):
                client.post("/checkout/request-code/", {"phone": phone})

            mock_vs.request_code.reset_mock()
            response = client.post("/checkout/request-code/", {"phone": phone})

            assert response.status_code == 429
            assert "Muitas tentativas" in response.content.decode()

    @override_settings(RATELIMIT_ENABLE=True)
    def test_rate_limit_blocks_excessive_verify_attempts(self, client: Client, customer):
        """VerifyCodeView blocks after 10 requests/min with HTTP 429."""
        phone = customer.phone

        with patch("shopman.doorman.services.verification.AuthService") as mock_vs:
            mock_vs.verify_for_login.return_value = type("R", (), {
                "success": False, "error": "Incorrect code.",
                "attempts_remaining": 9, "customer": None,
            })()

            for _ in range(10):
                client.post("/checkout/verify-code/", {"phone": phone, "code": "000000"})

            mock_vs.verify_for_login.reset_mock()
            response = client.post("/checkout/verify-code/", {"phone": phone, "code": "000000"})

            assert response.status_code == 429
            assert "Muitas tentativas" in response.content.decode()


# ── Django Auth ───────────────────────────────────────────────────


class TestDjangoAuth:
    """Auth via request.customer (middleware) protects account views."""

    def test_auth_protects_account_views(self, client: Client, customer):
        """AccountView redirects to login when not authenticated."""
        response = client.get("/minha-conta/")
        assert response.status_code == 302
        assert "/login/" in response.url

        # Log in via Django auth
        _login_as_customer(client, customer)

        response = client.get("/minha-conta/")
        assert response.status_code == 200
        assert response.context["customer"] is not None
        assert response.context["customer"].pk == customer.pk

    def test_auth_invalid_uuid_redirects(self, client: Client):
        """User with no CustomerUser link redirects to login."""
        user = User.objects.create_user(username="orphan", password="test")
        client.force_login(user)

        response = client.get("/minha-conta/")
        assert response.status_code == 302

    def test_verify_code_sets_django_auth(self, client: Client, customer):
        """Successful OTP verification sets Django auth (real service, no mock)."""
        from shopman.doorman.models import VerificationCode
        from shopman.doorman.models.verification_code import generate_raw_code

        raw_code, hmac_digest = generate_raw_code()
        VerificationCode.objects.create(
            code_hash=hmac_digest,
            target_value=customer.phone,
            purpose="login",
            status="sent",
        )

        response = client.post("/checkout/verify-code/", {
            "phone": customer.phone, "code": raw_code,
        })

        assert response.status_code == 200
        # Django auth user should be in session
        assert client.session.get("_auth_user_id") is not None

    def test_auth_get_shows_data_when_verified(self, client: Client, customer):
        """GET with auth shows full account data."""
        _login_as_customer(client, customer)

        response = client.get("/minha-conta/")
        assert response.status_code == 200
        assert response.context["customer"] is not None
        assert response.context["customer"].pk == customer.pk

    def test_auth_post_redirects_to_login(self, client: Client, customer):
        """POST without auth redirects to login."""
        response = client.post("/minha-conta/", {"phone": customer.phone})
        assert response.status_code == 302
        assert "/login/" in response.url


# ── Address Auth ──────────────────────────────────────────────────────


class TestAddressAuth:
    """Address CRUD requires auth — no phone fallback."""

    def test_address_create_requires_auth(self, client: Client, customer):
        """POST to create address without auth returns 401."""
        response = client.post("/minha-conta/enderecos/", {
            "formatted_address": "Rua Nova 456",
            "label": "work",
        })
        assert response.status_code == 401

    def test_address_update_requires_auth(self, client: Client, customer_address):
        """POST to update address without auth returns 401."""
        response = client.post(f"/minha-conta/enderecos/{customer_address.pk}/", {
            "formatted_address": "Rua Alterada 789",
        })
        assert response.status_code == 401

    def test_address_delete_requires_auth(self, client: Client, customer_address):
        """POST to delete address without auth returns 401."""
        response = client.post(f"/minha-conta/enderecos/{customer_address.pk}/delete/")
        assert response.status_code == 401

    def test_address_set_default_requires_auth(self, client: Client, customer_address):
        """POST to set default address without auth returns 401."""
        response = client.post(f"/minha-conta/enderecos/{customer_address.pk}/default/")
        assert response.status_code == 401

    def test_address_create_works_with_auth(self, client: Client, customer):
        """POST to create address WITH auth succeeds."""
        _login_as_customer(client, customer)

        response = client.post("/minha-conta/enderecos/", {
            "formatted_address": "Rua Nova 456 - Centro - Londrina",
            "label": "work",
        })
        assert response.status_code == 200
