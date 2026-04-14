"""
Security tests for Auth (H06).

Tests for:
- H01: OTP generation uses secrets (not random)
- H02: Open redirect prevention
- H03: Customer auto-creation setting
- H04: PII not leaked in logs
- H05: Access link API key authentication
- General: Rate limiting, token lifecycle, code lifecycle
"""

import json
from collections import Counter
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import RequestFactory, override_settings
from django.utils import timezone

from shopman.doorman.exceptions import GateError
from shopman.doorman.gates import Gates
from shopman.doorman.models import AccessLink, VerificationCode
from shopman.doorman.models.verification_code import generate_code, generate_raw_code, verify_code
from shopman.doorman.services.access_link import AccessLinkService
from shopman.doorman.services.verification import AuthService
from shopman.doorman.utils import safe_redirect_url
from shopman.doorman.views.access_link import AccessLinkCreateView, AccessLinkExchangeView

from .conftest import TEST_API_KEY

# ===================================================
# H01: OTP Generation Security
# ===================================================


class TestOTPGeneration:
    """Tests for secure OTP code generation."""

    def test_otp_raw_codes_are_6_digits(self):
        """All generated raw codes must be exactly 6 digits."""
        for _ in range(100):
            raw_code, digest = generate_raw_code()
            assert len(raw_code) == 6, f"Code '{raw_code}' is not 6 digits"
            assert raw_code.isdigit(), f"Code '{raw_code}' contains non-digits"

    def test_otp_stored_codes_are_hmac(self):
        """generate_code() returns HMAC digest, not plaintext."""
        digest = generate_code()
        assert len(digest) == 64  # SHA-256 hex digest
        assert not digest.isdigit()  # Not a raw 6-digit code

    def test_otp_codes_include_leading_zeros(self):
        """Codes starting with 0 must be properly zero-padded."""
        codes = [generate_raw_code()[0] for _ in range(1000)]
        leading_zeros = [c for c in codes if c.startswith("0")]
        assert len(leading_zeros) > 0, "No codes with leading zeros in 1000 samples"

    def test_otp_codes_have_reasonable_distribution(self):
        """Codes should not cluster around specific values."""
        codes = [int(generate_raw_code()[0]) for _ in range(1000)]
        buckets = Counter(c // 100_000 for c in codes)
        for bucket, count in buckets.items():
            assert 30 < count < 250, (
                f"Bucket {bucket} has {count} codes — distribution looks skewed"
            )

    def test_otp_uses_secrets_module(self):
        """Verify that generate_code uses secrets, not random."""
        import shopman.doorman.models.verification_code as vc_module

        assert hasattr(vc_module, "secrets"), "secrets module not imported"

    def test_hmac_verification_works(self):
        """verify_code correctly validates raw code against stored digest."""
        raw_code, digest = generate_raw_code()
        assert verify_code(digest, raw_code)
        assert not verify_code(digest, "000000" if raw_code != "000000" else "111111")

    def test_stored_code_not_plaintext(self, db):
        """Code stored in DB is HMAC, not the raw 6-digit code."""
        code_obj = VerificationCode.objects.create(
            target_value="+5541999999999",
            purpose=VerificationCode.Purpose.LOGIN,
        )
        # The stored code is a 64-char HMAC digest
        assert len(code_obj.code_hash) == 64
        assert not code_obj.code_hash.isdigit()


# ===================================================
# H02: Open Redirect Prevention
# ===================================================


class TestSafeRedirectUrl:
    """Tests for safe_redirect_url utility."""

    def test_rejects_external_url(self):
        result = safe_redirect_url("https://evil.com/steal")
        assert result == "/"

    def test_rejects_http_external(self):
        result = safe_redirect_url("http://evil.com")
        assert result == "/"

    def test_rejects_protocol_relative(self):
        result = safe_redirect_url("//evil.com")
        assert result == "/"

    def test_accepts_relative_path(self):
        factory = RequestFactory()
        request = factory.get("/")
        result = safe_redirect_url("/checkout/", request)
        assert result == "/checkout/"

    def test_accepts_root_path(self):
        result = safe_redirect_url("/")
        assert result == "/"

    def test_none_returns_fallback(self):
        result = safe_redirect_url(None)
        assert result == "/"

    def test_empty_returns_fallback(self):
        result = safe_redirect_url("")
        assert result == "/"

    def test_rejects_javascript_scheme(self):
        result = safe_redirect_url("javascript:alert(1)")
        assert result == "/"

    def test_rejects_data_scheme(self):
        result = safe_redirect_url("data:text/html,<h1>evil</h1>")
        assert result == "/"

    @override_settings(DOORMAN={"ALLOWED_REDIRECT_HOSTS": {"trusted.com"}})
    def test_accepts_allowed_host(self):
        result = safe_redirect_url("https://trusted.com/page")
        assert result == "https://trusted.com/page"


# ===================================================
# H05: Access Link API Key Authentication
# ===================================================


@pytest.mark.django_db
class TestAccessLinkCreateAuth:
    """Tests for access link creation endpoint authentication.

    Uses RequestFactory + View.as_view() directly to avoid URL registration issues.
    """

    def _post_create(self, data, headers=None):
        """Helper to POST to AccessLinkCreateView.

        Mocks _build_url to avoid reverse() failing when auth URLs
        are not registered in the test project.
        """
        factory = RequestFactory()
        body = json.dumps(data)
        kwargs = {"content_type": "application/json"}
        if headers:
            kwargs.update(headers)
        request = factory.post("/auth/access-link/create/", body, **kwargs)
        view = AccessLinkCreateView.as_view()
        with patch.object(
            AccessLinkService,
            "_build_url",
            return_value="https://test.local/auth/access-link/?t=mock",
        ):
            return view(request)

    @override_settings(DOORMAN={"ACCESS_LINK_API_KEY": TEST_API_KEY})
    def test_create_without_key_returns_401(self, customer):
        """POST without API key must return 401."""
        response = self._post_create({"customer_id": str(customer.uuid)})
        assert response.status_code == 401

    @override_settings(DOORMAN={"ACCESS_LINK_API_KEY": TEST_API_KEY})
    def test_create_with_wrong_key_returns_401(self, customer):
        """POST with wrong API key must return 401."""
        response = self._post_create(
            {"customer_id": str(customer.uuid)},
            headers={"HTTP_AUTHORIZATION": "Bearer wrong-key"},
        )
        assert response.status_code == 401

    @override_settings(DOORMAN={"ACCESS_LINK_API_KEY": TEST_API_KEY})
    def test_create_with_bearer_key_returns_200(self, customer):
        """POST with correct Bearer key must succeed."""
        response = self._post_create(
            {"customer_id": str(customer.uuid)},
            headers={"HTTP_AUTHORIZATION": f"Bearer {TEST_API_KEY}"},
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "token" in data
        assert "url" in data

    @override_settings(DOORMAN={"ACCESS_LINK_API_KEY": TEST_API_KEY})
    def test_create_with_x_api_key_returns_200(self, customer):
        """POST with X-Api-Key header must succeed."""
        response = self._post_create(
            {"customer_id": str(customer.uuid)},
            headers={"HTTP_X_API_KEY": TEST_API_KEY},
        )
        assert response.status_code == 200

    @override_settings(DOORMAN={"ACCESS_LINK_API_KEY": ""})
    def test_create_without_configured_key_allows_access(self, customer):
        """POST without configured API key must allow access (dev mode)."""
        response = self._post_create({"customer_id": str(customer.uuid)})
        assert response.status_code == 200


# ===================================================
# Access Link Lifecycle
# ===================================================


@pytest.mark.django_db
class TestAccessLinkLifecycle:
    """Tests for access link security lifecycle."""

    def _make_request(self):
        """Create a request with session support."""
        from django.contrib.sessions.backends.db import SessionStore

        factory = RequestFactory()
        request = factory.get("/")
        request.session = SessionStore()
        return request

    def test_token_single_use(self, customer, access_link):
        """Token must not be usable after first exchange."""
        # First exchange: should succeed
        request1 = self._make_request()
        result1 = AccessLinkService.exchange(access_link._raw_token, request1)
        assert result1.success

        # Move used_at past the reuse window
        access_link.refresh_from_db()
        access_link.used_at = timezone.now() - timedelta(seconds=120)
        access_link.save()

        # Second exchange: should fail
        request2 = self._make_request()
        result2 = AccessLinkService.exchange(access_link._raw_token, request2)
        assert not result2.success

    def test_expired_token_rejected(self, expired_access_link):
        """Expired token must be rejected."""
        request = self._make_request()
        result = AccessLinkService.exchange(expired_access_link._raw_token, request)
        assert not result.success
        assert "expired" in result.error.lower()

    def test_exchange_redirects_safely(self, customer, access_link):
        """Exchange with malicious next URL must use safe_redirect_url."""
        factory = RequestFactory()
        request = factory.get(
            "/auth/access-link/",
            {"t": access_link._raw_token, "next": "https://evil.com"},
        )
        from django.contrib.sessions.backends.db import SessionStore

        request.session = SessionStore()

        view = AccessLinkExchangeView.as_view()
        response = view(request)

        assert response.status_code == 302
        assert "evil.com" not in response["Location"]

    def test_invalid_token_does_not_redirect(self):
        """Invalid token must NOT redirect (should show error)."""
        factory = RequestFactory()
        request = factory.get("/auth/access-link/", {"t": "invalid-token-123"})
        from django.contrib.sessions.backends.db import SessionStore

        request.session = SessionStore()

        view = AccessLinkExchangeView.as_view()
        # Mock render to avoid template not found in test project
        with patch("shopman.doorman.views.access_link.render", return_value=None) as mock_render:
            view(request)
            # Should call render (error page), not redirect
            mock_render.assert_called_once()
            # Verify error message was passed
            _args, kwargs = mock_render.call_args
            # render(request, template, context) - context should have "error"
            context = _args[2] if len(_args) > 2 else kwargs.get("context", {})
            assert "error" in context


# ===================================================
# Verification Code Lifecycle
# ===================================================


@pytest.mark.django_db
class TestVerificationCodeLifecycle:
    """Tests for verification code security lifecycle."""

    def test_brute_force_blocked_after_max_attempts(self, verification_code):
        """Code must be blocked after max attempts."""
        for i in range(verification_code.max_attempts):
            verification_code.record_attempt()

        verification_code.refresh_from_db()
        assert not verification_code.is_valid
        assert verification_code.status == VerificationCode.Status.FAILED

    def test_expired_code_rejected(self, expired_verification_code):
        """Expired code must be rejected."""
        assert expired_verification_code.is_expired
        assert not expired_verification_code.is_valid

    def test_verify_wrong_code_records_attempt(self, customer, verification_code):
        """Wrong code must record attempt and return remaining."""
        wrong_code = "000000" if verification_code._raw_code != "000000" else "111111"
        result = AuthService.verify_for_login(
            "+5541999999999", wrong_code, None
        )
        assert not result.success
        assert result.attempts_remaining is not None

    def test_verify_correct_code_succeeds(self, customer, verification_code):
        """Correct code must verify and return customer."""
        result = AuthService.verify_for_login(
            "+5541999999999", verification_code._raw_code, None
        )
        assert result.success
        assert result.customer is not None

    def test_rate_limit_by_phone(self, db):
        """Rate limit must block after too many requests per phone."""
        phone = "+5541777777777"
        for i in range(5):
            VerificationCode.objects.create(
                target_value=phone,
                purpose=VerificationCode.Purpose.LOGIN,
            )

        with pytest.raises(GateError):
            Gates.rate_limit(phone, max_requests=5, window_minutes=15)

    def test_rate_limit_by_ip(self, db):
        """Rate limit must block after too many requests per IP."""
        ip = "192.168.1.100"
        for i in range(20):
            VerificationCode.objects.create(
                target_value=f"+554199{i:07d}",
                purpose=VerificationCode.Purpose.LOGIN,
                ip_address=ip,
            )

        with pytest.raises(GateError):
            Gates.ip_rate_limit(ip, max_requests=20, window_minutes=60)


# ===================================================
# H03: Customer Auto-Creation
# ===================================================


@pytest.mark.django_db
class TestCustomerAutoCreation:
    """Tests for customer auto-creation setting."""

    @override_settings(DOORMAN={"AUTO_CREATE_CUSTOMER": False})
    def test_auto_create_disabled_returns_error(self, db):
        """When disabled, unknown phone must return error."""
        unknown_phone = "+5541666666666"
        raw_code, hmac_digest = generate_raw_code()
        code = VerificationCode.objects.create(
            code_hash=hmac_digest,
            target_value=unknown_phone,
            purpose=VerificationCode.Purpose.LOGIN,
        )
        code.mark_sent()

        result = AuthService.verify_for_login(
            unknown_phone, raw_code, None
        )
        assert not result.success
        assert "not found" in result.error.lower()

    def test_auto_create_enabled_creates_customer(self, db):
        """When enabled (default), unknown phone must create customer."""
        unknown_phone = "+5541555555555"
        raw_code, hmac_digest = generate_raw_code()
        code = VerificationCode.objects.create(
            code_hash=hmac_digest,
            target_value=unknown_phone,
            purpose=VerificationCode.Purpose.LOGIN,
        )
        code.mark_sent()

        result = AuthService.verify_for_login(
            unknown_phone, raw_code, None
        )
        assert result.success
        assert result.customer is not None
        assert result.created_customer is True


# ===================================================
# H04: PII Logging
# ===================================================


@pytest.mark.django_db
class TestPIILogging:
    """Tests that session values are not logged."""

    def test_session_values_not_in_info_logs(self, customer, access_link):
        """Session preservation must not log values at INFO level."""
        from django.contrib.sessions.backends.db import SessionStore

        factory = RequestFactory()
        request = factory.get("/")
        request.session = SessionStore()
        secret_value = "super-secret-basket-key-12345"
        request.session["basket_key"] = secret_value
        request.session.save()

        with patch("shopman.doorman.services.access_link.logger") as mock_logger:
            AccessLinkService.exchange(
                access_link._raw_token,
                request,
                preserve_session_keys=["basket_key"],
            )

            # Check that no INFO log contains the secret value
            for call in mock_logger.info.call_args_list:
                args_str = str(call)
                assert secret_value not in args_str, (
                    f"Secret value found in INFO log: {args_str}"
                )


# ===================================================
# Gate Validations
# ===================================================


@pytest.mark.django_db
class TestGates:
    """Tests for Auth gates."""

    def test_g7_valid_token_passes(self, access_link):
        result = Gates.access_link_validity(access_link)
        assert result.passed

    def test_g7_expired_token_raises(self, expired_access_link):
        with pytest.raises(GateError, match="expired"):
            Gates.access_link_validity(expired_access_link)

    def test_g7_used_token_raises(self, customer, access_link, django_user_model):
        user = django_user_model.objects.create_user(username="gateuser")
        access_link.mark_used(user)
        access_link.used_at = timezone.now() - timedelta(seconds=120)
        access_link.save()

        with pytest.raises(GateError, match="already used"):
            Gates.access_link_validity(access_link)

    def test_g7_wrong_audience_raises(self, access_link):
        with pytest.raises(GateError, match="audience"):
            Gates.access_link_validity(
                access_link,
                required_audience=AccessLink.Audience.WEB_CHECKOUT,
            )

    def test_g8_valid_code_passes(self, verification_code):
        result = Gates.verification_code_validity(verification_code)
        assert result.passed

    def test_g8_expired_code_raises(self, expired_verification_code):
        with pytest.raises(GateError, match="expired"):
            Gates.verification_code_validity(expired_verification_code)

    def test_g8_max_attempts_raises(self, verification_code):
        verification_code.attempts = verification_code.max_attempts
        verification_code.save()
        with pytest.raises(GateError, match="attempts"):
            Gates.verification_code_validity(verification_code)

    def test_g9_within_limit_passes(self, db):
        result = Gates.rate_limit("+5541999999999", max_requests=5, window_minutes=15)
        assert result.passed

    def test_g10_no_ip_passes(self, db):
        result = Gates.ip_rate_limit("")
        assert result.passed

    def test_g12_access_link_rate_limit_passes(self, db):
        """G12 passes when within limit."""
        result = Gates.access_link_rate_limit("test@example.com", max_requests=5, window_minutes=15)
        assert result.passed

    def test_g12_access_link_rate_limit_exceeded(self, customer):
        """G12 blocks after too many access link tokens for same email."""
        email = customer.email
        for _ in range(5):
            AccessLink.create_with_token(
                customer_id=customer.uuid,
                metadata={"method": "access_link", "email": email},
            )
        with pytest.raises(GateError, match="Rate limit"):
            Gates.access_link_rate_limit(email, max_requests=5, window_minutes=15)


# ===================================================
# AccessLinkService Utilities
# ===================================================


@pytest.mark.django_db
class TestAccessLinkUtilities:
    """Tests for AccessLinkService utility methods."""

    def test_get_customer_for_user_with_link(self, customer, access_link):
        """get_customer_for_user returns customer when CustomerUser exists."""
        from django.contrib.sessions.backends.db import SessionStore

        factory = RequestFactory()
        request = factory.get("/")
        request.session = SessionStore()
        result = AccessLinkService.exchange(access_link._raw_token, request)
        assert result.success

        found = AccessLinkService.get_customer_for_user(result.user)
        assert found is not None
        assert found.uuid == customer.uuid

    def test_get_customer_for_user_without_link(self, django_user_model):
        """get_customer_for_user returns None when no CustomerUser."""
        user = django_user_model.objects.create_user(username="nolink")
        assert AccessLinkService.get_customer_for_user(user) is None

    def test_get_user_for_customer_with_link(self, customer, access_link):
        """get_user_for_customer returns user when CustomerUser exists."""
        from django.contrib.sessions.backends.db import SessionStore

        factory = RequestFactory()
        request = factory.get("/")
        request.session = SessionStore()
        result = AccessLinkService.exchange(access_link._raw_token, request)
        assert result.success

        user = AccessLinkService.get_user_for_customer(customer)
        assert user is not None
        assert user.id == result.user.id

    def test_get_user_for_customer_without_link(self, customer):
        """get_user_for_customer returns None when no CustomerUser."""
        assert AccessLinkService.get_user_for_customer(customer) is None

    def test_cleanup_expired_tokens(self, db):
        """cleanup_expired_tokens deletes old expired tokens."""
        import uuid

        # Create an expired token old enough to be cleaned
        link, _ = AccessLink.create_with_token(
            customer_id=uuid.uuid4(),
            expires_at=timezone.now() - timedelta(days=10),
        )
        deleted = AccessLinkService.cleanup_expired_tokens(days=7)
        assert deleted == 1
        assert not AccessLink.objects.filter(pk=link.pk).exists()

    def test_cleanup_does_not_delete_recent(self, db):
        """cleanup_expired_tokens preserves recently expired tokens."""
        import uuid

        link, _ = AccessLink.create_with_token(
            customer_id=uuid.uuid4(),
            expires_at=timezone.now() - timedelta(days=1),
        )
        deleted = AccessLinkService.cleanup_expired_tokens(days=7)
        assert deleted == 0
        assert AccessLink.objects.filter(pk=link.pk).exists()

    def test_integrity_error_retry(self, customer):
        """_get_or_create_user handles concurrent creation via IntegrityError."""

        from django.contrib.auth import get_user_model

        from shopman.doorman.models import CustomerUser

        User = get_user_model()
        # Pre-create user and link to simulate concurrent creation
        existing_user = User.objects.create_user(username="existing_concurrent")
        CustomerUser.objects.create(user=existing_user, customer_id=customer.uuid)

        # Now try _get_or_create_user — should find existing link
        user, created = AccessLinkService._get_or_create_user(customer)
        assert not created
        assert user.id == existing_user.id
