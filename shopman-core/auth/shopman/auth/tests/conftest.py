"""Auth test fixtures."""

from datetime import timedelta

import pytest
from django.utils import timezone

from shopman.customers.models import Customer

from shopman.auth.models import AccessLink, VerificationCode
from shopman.auth.models.verification_code import generate_raw_code


TEST_API_KEY = "test-auth-api-key-2026"


@pytest.fixture
def customer(db):
    """Create a test customer."""
    return Customer.objects.create(
        ref="TEST-001",
        first_name="Test",
        last_name="Customer",
        phone="5541999999999",
        email="test@example.com",
    )


@pytest.fixture
def other_customer(db):
    """Create another test customer."""
    return Customer.objects.create(
        ref="TEST-002",
        first_name="Other",
        last_name="Customer",
        phone="5541888888888",
        email="other@example.com",
    )


@pytest.fixture
def access_link(customer):
    """Create a valid access link."""
    return AccessLink.objects.create(
        customer_id=customer.uuid,
        audience=AccessLink.Audience.WEB_GENERAL,
        source=AccessLink.Source.MANYCHAT,
    )


@pytest.fixture
def expired_access_link(customer):
    """Create an expired access link."""
    return AccessLink.objects.create(
        customer_id=customer.uuid,
        expires_at=timezone.now() - timedelta(minutes=1),
    )


@pytest.fixture
def verification_code(db):
    """Create a valid verification code.

    The raw 6-digit code is stored as ``code._raw_code`` so tests
    can pass it to ``verify_for_login`` while the DB stores the HMAC.
    """
    raw_code, hmac_digest = generate_raw_code()
    code = VerificationCode.objects.create(
        code_hash=hmac_digest,
        target_value="+5541999999999",
        purpose=VerificationCode.Purpose.LOGIN,
    )
    code.mark_sent()
    code._raw_code = raw_code
    return code


@pytest.fixture
def expired_verification_code(db):
    """Create an expired verification code."""
    return VerificationCode.objects.create(
        target_value="+5541999999999",
        purpose=VerificationCode.Purpose.LOGIN,
        expires_at=timezone.now() - timedelta(minutes=1),
    )
