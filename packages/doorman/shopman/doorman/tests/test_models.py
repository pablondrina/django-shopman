"""Tests for Auth models."""

import pytest
from django.utils import timezone

from shopman.doorman.models import AccessLink, VerificationCode


@pytest.mark.django_db
class TestAccessLink:
    def test_create_access_link(self, customer):
        """Test creating an access link with hashed token."""
        link, raw_token = AccessLink.create_with_token(
            customer_id=customer.uuid,
            audience=AccessLink.Audience.WEB_GENERAL,
            source=AccessLink.Source.MANYCHAT,
        )
        assert link.token_hash is not None
        assert len(link.token_hash) == 64  # HMAC-SHA256 hex digest
        assert raw_token is not None
        assert len(raw_token) > 20
        assert link.is_valid
        assert not link.is_expired

    def test_access_link_lookup_by_token(self, customer):
        """Test looking up access link by raw token."""
        link, raw_token = AccessLink.create_with_token(
            customer_id=customer.uuid,
        )
        found = AccessLink.get_by_token(raw_token)
        assert found is not None
        assert found.pk == link.pk

    def test_access_link_lookup_wrong_token(self, customer):
        """Test that wrong token returns None."""
        AccessLink.create_with_token(customer_id=customer.uuid)
        found = AccessLink.get_by_token("wrong-token-value")
        assert found is None

    def test_access_link_expires(self, customer):
        """Test token expiration."""
        link, _ = AccessLink.create_with_token(
            customer_id=customer.uuid,
            expires_at=timezone.now() - timezone.timedelta(minutes=1),
        )
        assert link.is_expired
        assert not link.is_valid

    def test_access_link_mark_used(self, customer, django_user_model):
        """Test marking token as used."""
        user = django_user_model.objects.create_user(username="testuser")
        link, _ = AccessLink.create_with_token(customer_id=customer.uuid)

        link.mark_used(user)
        link.refresh_from_db()

        assert link.used_at is not None
        assert link.user == user
        assert not link.is_valid


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
