"""Tests for Auth models."""

import pytest
from django.utils import timezone

from shopman.auth.models import AccessLink, VerificationCode


@pytest.mark.django_db
class TestAccessLink:
    def test_create_access_link(self, customer):
        """Test creating an access link."""
        token = AccessLink.objects.create(
            customer_id=customer.uuid,
            audience=AccessLink.Audience.WEB_GENERAL,
            source=AccessLink.Source.MANYCHAT,
        )
        assert token.token is not None
        assert len(token.token) > 20
        assert token.is_valid
        assert not token.is_expired

    def test_access_link_expires(self, customer):
        """Test token expiration."""
        token = AccessLink.objects.create(
            customer_id=customer.uuid,
            expires_at=timezone.now() - timezone.timedelta(minutes=1),
        )
        assert token.is_expired
        assert not token.is_valid

    def test_access_link_mark_used(self, customer, django_user_model):
        """Test marking token as used."""
        user = django_user_model.objects.create_user(username="testuser")
        token = AccessLink.objects.create(customer_id=customer.uuid)

        token.mark_used(user)
        token.refresh_from_db()

        assert token.used_at is not None
        assert token.user == user
        assert not token.is_valid


@pytest.mark.django_db
class TestVerificationCode:
    def test_create_verification_code(self):
        """Test creating a verification code."""
        code = VerificationCode.objects.create(
            target_value="+5541999999999",
            purpose=VerificationCode.Purpose.LOGIN,
        )
        assert code.code_hash is not None
        assert len(code.code_hash) == 64  # HMAC-SHA256 hex digest
        assert code.is_valid
        assert code.attempts_remaining == 5

    def test_verification_code_attempts(self):
        """Test recording attempts."""
        code = VerificationCode.objects.create(
            target_value="+5541999999999",
            max_attempts=3,
        )

        code.record_attempt()
        assert code.attempts == 1
        assert code.attempts_remaining == 2
        assert code.is_valid

        code.record_attempt()
        code.record_attempt()

        assert code.attempts == 3
        assert code.status == VerificationCode.Status.FAILED
        assert not code.is_valid

    def test_verification_code_verify(self):
        """Test marking code as verified."""
        import uuid

        code = VerificationCode.objects.create(target_value="+5541999999999")
        customer_id = uuid.uuid4()

        code.mark_verified(customer_id)
        code.refresh_from_db()

        assert code.status == VerificationCode.Status.VERIFIED
        assert code.verified_at is not None
        assert code.customer_id == customer_id
