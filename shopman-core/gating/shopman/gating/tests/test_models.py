"""Tests for Gating models."""

import pytest
from django.utils import timezone

from shopman.gating.models import BridgeToken, MagicCode


@pytest.mark.django_db
class TestBridgeToken:
    def test_create_bridge_token(self, customer):
        """Test creating a bridge token."""
        token = BridgeToken.objects.create(
            customer_id=customer.uuid,
            audience=BridgeToken.Audience.WEB_GENERAL,
            source=BridgeToken.Source.MANYCHAT,
        )
        assert token.token is not None
        assert len(token.token) > 20
        assert token.is_valid
        assert not token.is_expired

    def test_bridge_token_expires(self, customer):
        """Test token expiration."""
        token = BridgeToken.objects.create(
            customer_id=customer.uuid,
            expires_at=timezone.now() - timezone.timedelta(minutes=1),
        )
        assert token.is_expired
        assert not token.is_valid

    def test_bridge_token_mark_used(self, customer, django_user_model):
        """Test marking token as used."""
        user = django_user_model.objects.create_user(username="testuser")
        token = BridgeToken.objects.create(customer_id=customer.uuid)

        token.mark_used(user)
        token.refresh_from_db()

        assert token.used_at is not None
        assert token.user == user
        assert not token.is_valid


@pytest.mark.django_db
class TestMagicCode:
    def test_create_magic_code(self):
        """Test creating a magic code."""
        code = MagicCode.objects.create(
            target_value="+5541999999999",
            purpose=MagicCode.Purpose.LOGIN,
        )
        assert code.code_hash is not None
        assert len(code.code_hash) == 64  # HMAC-SHA256 hex digest
        assert code.is_valid
        assert code.attempts_remaining == 5

    def test_magic_code_attempts(self):
        """Test recording attempts."""
        code = MagicCode.objects.create(
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
        assert code.status == MagicCode.Status.FAILED
        assert not code.is_valid

    def test_magic_code_verify(self):
        """Test marking code as verified."""
        import uuid

        code = MagicCode.objects.create(target_value="+5541999999999")
        customer_id = uuid.uuid4()

        code.mark_verified(customer_id)
        code.refresh_from_db()

        assert code.status == MagicCode.Status.VERIFIED
        assert code.verified_at is not None
        assert code.customer_id == customer_id
