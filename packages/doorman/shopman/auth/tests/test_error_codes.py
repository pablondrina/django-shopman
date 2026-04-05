"""
Tests for error codes and settings validation (AUTH-4).

Tests:
- Each error path in AuthService returns the correct ErrorCode
- Each error path in AccessLinkService returns the correct ErrorCode
- Settings validation catches invalid values
- Settings validation passes for valid defaults
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone

from shopman.auth.conf import validate_settings
from shopman.auth.error_codes import ErrorCode
from shopman.auth.models import AccessLink, VerificationCode
from shopman.auth.models.verification_code import generate_raw_code
from shopman.auth.services.access_link import AccessLinkService
from shopman.auth.services.verification import AuthService


# ===========================================
# AuthService error codes
# ===========================================


@pytest.mark.django_db
def test_request_code_rate_limit_error_code(customer):
    """G9 rate limit returns RATE_LIMIT error code."""
    from shopman.auth.exceptions import GateError

    with patch("shopman.auth.services.verification.Gates.rate_limit", side_effect=GateError("G9")):
        result = AuthService.request_code(
            target_value=customer.phone,
            sender=type("S", (), {"send_code": lambda *a: True})(),
        )
    assert not result.success
    assert result.error_code == ErrorCode.RATE_LIMIT


@pytest.mark.django_db
def test_request_code_cooldown_error_code(customer):
    """G11 cooldown returns COOLDOWN error code."""
    from shopman.auth.exceptions import GateError

    with patch("shopman.auth.services.verification.Gates.code_cooldown", side_effect=GateError("G11")):
        result = AuthService.request_code(
            target_value=customer.phone,
            sender=type("S", (), {"send_code": lambda *a: True})(),
        )
    assert not result.success
    assert result.error_code == ErrorCode.COOLDOWN


@pytest.mark.django_db
def test_request_code_ip_rate_limit_error_code(customer):
    """G10 IP rate limit returns IP_RATE_LIMIT error code."""
    from shopman.auth.exceptions import GateError

    with patch("shopman.auth.services.verification.Gates.ip_rate_limit", side_effect=GateError("G10")):
        result = AuthService.request_code(
            target_value=customer.phone,
            ip_address="1.2.3.4",
            sender=type("S", (), {"send_code": lambda *a: True})(),
        )
    assert not result.success
    assert result.error_code == ErrorCode.IP_RATE_LIMIT


@pytest.mark.django_db
def test_request_code_send_failed_error_code(customer):
    """Failed send returns SEND_FAILED error code."""
    result = AuthService.request_code(
        target_value=customer.phone,
        sender=type("S", (), {"send_code": lambda *a: False})(),
    )
    assert not result.success
    assert result.error_code == ErrorCode.SEND_FAILED


@pytest.mark.django_db
def test_request_code_send_exception_error_code(customer):
    """Send exception returns SEND_FAILED error code."""
    def raise_exc(*a):
        raise RuntimeError("fail")

    result = AuthService.request_code(
        target_value=customer.phone,
        sender=type("S", (), {"send_code": raise_exc})(),
    )
    assert not result.success
    assert result.error_code == ErrorCode.SEND_FAILED


@pytest.mark.django_db
def test_verify_code_expired_error_code(customer):
    """Expired code returns CODE_EXPIRED error code."""
    result = AuthService.verify_for_login(
        target_value=customer.phone,
        code_input="123456",
    )
    assert not result.success
    assert result.error_code == ErrorCode.CODE_EXPIRED


@pytest.mark.django_db
def test_verify_code_invalid_error_code(customer, verification_code):
    """Incorrect code returns CODE_INVALID error code."""
    result = AuthService.verify_for_login(
        target_value=verification_code.target_value,
        code_input="000000",
    )
    assert not result.success
    assert result.error_code == ErrorCode.CODE_INVALID


@pytest.mark.django_db
@override_settings(AUTH={"AUTO_CREATE_CUSTOMER": False})
def test_verify_account_not_found_error_code():
    """Unknown phone with auto-create disabled returns ACCOUNT_NOT_FOUND."""
    raw_code, hmac_digest = generate_raw_code()
    VerificationCode.objects.create(
        code_hash=hmac_digest,
        target_value="+5500000000000",
        purpose=VerificationCode.Purpose.LOGIN,
        status=VerificationCode.Status.SENT,
    )

    result = AuthService.verify_for_login(
        target_value="+5500000000000",
        code_input=raw_code,
    )
    assert not result.success
    assert result.error_code == ErrorCode.ACCOUNT_NOT_FOUND


@pytest.mark.django_db
def test_verify_success_no_error_code(customer, verification_code):
    """Successful verification has no error code."""
    result = AuthService.verify_for_login(
        target_value=verification_code.target_value,
        code_input=verification_code._raw_code,
    )
    assert result.success
    assert result.error_code is None


# ===========================================
# AccessLinkService error codes
# ===========================================


@pytest.mark.django_db
def test_exchange_invalid_token_error_code():
    """Invalid token returns TOKEN_INVALID."""
    from django.test import RequestFactory
    from django.contrib.sessions.backends.db import SessionStore
    from django.contrib.auth.models import AnonymousUser

    factory = RequestFactory()
    request = factory.get("/")
    request.session = SessionStore()
    request.session.create()
    request.user = AnonymousUser()

    result = AccessLinkService.exchange("nonexistent-token", request)
    assert not result.success
    assert result.error_code == ErrorCode.TOKEN_INVALID


@pytest.mark.django_db
def test_exchange_expired_token_error_code(customer):
    """Expired token returns TOKEN_EXPIRED."""
    from django.test import RequestFactory
    from django.contrib.sessions.backends.db import SessionStore
    from django.contrib.auth.models import AnonymousUser

    token = AccessLink.objects.create(
        customer_id=customer.uuid,
        expires_at=timezone.now() - timedelta(minutes=1),
    )

    factory = RequestFactory()
    request = factory.get("/")
    request.session = SessionStore()
    request.session.create()
    request.user = AnonymousUser()

    result = AccessLinkService.exchange(token.token, request)
    assert not result.success
    assert result.error_code == ErrorCode.TOKEN_EXPIRED


@override_settings(AUTH={"ACCESS_LINK_ENABLED": False})
def test_send_access_link_disabled_error_code():
    """Disabled access links return ACCESS_LINK_DISABLED."""
    result = AccessLinkService.send_access_link("test@example.com")
    assert not result.success
    assert result.error_code == ErrorCode.ACCESS_LINK_DISABLED


def test_send_access_link_invalid_email_error_code():
    """Invalid email returns INVALID_EMAIL."""
    result = AccessLinkService.send_access_link("not-an-email")
    assert not result.success
    assert result.error_code == ErrorCode.INVALID_EMAIL


@pytest.mark.django_db
def test_send_access_link_unknown_email_error_code():
    """Unknown email returns ACCOUNT_NOT_FOUND."""
    result = AccessLinkService.send_access_link("unknown@example.com")
    assert not result.success
    assert result.error_code == ErrorCode.ACCOUNT_NOT_FOUND


@pytest.mark.django_db
def test_send_access_link_inactive_error_code(customer):
    """Inactive customer returns ACCOUNT_INACTIVE."""
    from shopman.auth.protocols.customer import AuthCustomerInfo

    inactive = AuthCustomerInfo(
        uuid=customer.uuid, name="Test", phone=None,
        email=customer.email, is_active=False,
    )
    with patch("shopman.auth.adapter.DefaultAuthAdapter.resolve_customer_by_email", return_value=inactive):
        result = AccessLinkService.send_access_link(customer.email)
    assert not result.success
    assert result.error_code == ErrorCode.ACCOUNT_INACTIVE


# ===========================================
# Settings validation
# ===========================================


def test_validate_settings_defaults_pass():
    """Default settings should pass validation."""
    errors = validate_settings()
    assert errors == []


@override_settings(AUTH={"ACCESS_LINK_EXCHANGE_TTL_MINUTES": 0})
def test_validate_settings_invalid_exchange_ttl():
    errors = validate_settings()
    assert any("ACCESS_LINK_EXCHANGE_TTL_MINUTES" in e for e in errors)


@override_settings(AUTH={"ACCESS_CODE_TTL_MINUTES": -1})
def test_validate_settings_invalid_code_ttl():
    errors = validate_settings()
    assert any("ACCESS_CODE_TTL_MINUTES" in e for e in errors)


@override_settings(AUTH={"ACCESS_CODE_MAX_ATTEMPTS": 0})
def test_validate_settings_invalid_max_attempts():
    errors = validate_settings()
    assert any("ACCESS_CODE_MAX_ATTEMPTS" in e for e in errors)


@override_settings(AUTH={"ACCESS_CODE_RATE_LIMIT_MAX": 0})
def test_validate_settings_invalid_rate_limit():
    errors = validate_settings()
    assert any("ACCESS_CODE_RATE_LIMIT_MAX" in e for e in errors)


@override_settings(AUTH={"ACCESS_LINK_TTL_MINUTES": -5})
def test_validate_settings_invalid_access_link_ttl():
    errors = validate_settings()
    assert any("ACCESS_LINK_TTL_MINUTES" in e for e in errors)


@override_settings(AUTH={"DEVICE_TRUST_TTL_DAYS": 0})
def test_validate_settings_invalid_device_trust_ttl():
    errors = validate_settings()
    assert any("DEVICE_TRUST_TTL_DAYS" in e for e in errors)
