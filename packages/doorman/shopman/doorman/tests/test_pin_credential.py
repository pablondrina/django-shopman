"""Tests for the PinCredential generic auth primitive."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from shopman.doorman.models import PinCredential
from shopman.doorman.models.pin_credential import (
    PinCredentialError,
    hash_pin,
    pin_matches,
)

User = get_user_model()


@pytest.fixture
def operator(db):
    return User.objects.create_user(username="operador", password="x")


class TestPinHashingPrimitive:
    def test_hash_is_deterministic_and_not_plaintext(self):
        digest = hash_pin("1234")
        assert digest == hash_pin("1234")
        assert digest != "1234"
        assert len(digest) == 64  # sha256 hex

    def test_pin_matches_constant_time_compare(self):
        digest = hash_pin("4321")
        assert pin_matches(digest, "4321")
        assert not pin_matches(digest, "0000")

    def test_whitespace_is_trimmed(self):
        assert pin_matches(hash_pin("1234"), " 1234 ")


@pytest.mark.django_db
class TestPinCredential:
    def test_set_and_verify(self, operator):
        cred = PinCredential.set_for(operator, "1234")
        assert cred.pin_hash and cred.pin_hash != "1234"
        assert cred.verify("1234") is True

    def test_wrong_pin_increments_attempts(self, operator):
        cred = PinCredential.set_for(operator, "1234")
        assert cred.verify("0000") is False
        cred.refresh_from_db()
        assert cred.attempts == 1
        assert cred.attempts_remaining == cred.max_attempts - 1

    def test_lockout_after_max_attempts(self, operator):
        cred = PinCredential.set_for(operator, "1234")
        for _ in range(cred.max_attempts):
            cred.verify("0000")
        cred.refresh_from_db()
        assert cred.is_locked is True
        # correct PIN is rejected while locked
        assert cred.verify("1234") is False

    def test_unlock_clears_lockout(self, operator):
        cred = PinCredential.set_for(operator, "1234")
        for _ in range(cred.max_attempts):
            cred.verify("0000")
        cred.refresh_from_db()
        assert cred.is_locked
        cred.unlock()
        assert cred.is_locked is False
        assert cred.attempts == 0
        assert cred.verify("1234") is True

    def test_expired_lockout_allows_verify(self, operator):
        cred = PinCredential.set_for(operator, "1234")
        cred.locked_until = timezone.now() - timedelta(minutes=1)
        cred.save(update_fields=["locked_until"])
        assert cred.is_locked is False
        assert cred.verify("1234") is True

    def test_success_resets_attempts(self, operator):
        cred = PinCredential.set_for(operator, "1234")
        cred.verify("0000")
        assert cred.verify("1234") is True
        cred.refresh_from_db()
        assert cred.attempts == 0
        assert cred.last_verified_at is not None

    def test_rotation_resets_state(self, operator):
        cred = PinCredential.set_for(operator, "1234")
        cred.verify("0000")
        cred = PinCredential.set_for(operator, "5678")  # rotate
        assert cred.attempts == 0
        assert cred.verify("5678") is True
        assert cred.verify("1234") is False  # old PIN no longer valid (after this failure)

    def test_one_pin_per_user(self, operator):
        PinCredential.set_for(operator, "1234")
        PinCredential.set_for(operator, "9999")
        assert PinCredential.objects.filter(user=operator).count() == 1

    def test_policy_min_length(self, operator):
        with pytest.raises(PinCredentialError):
            PinCredential.set_for(operator, "12")  # below default min length 4

    def test_policy_digits_only(self, operator):
        with pytest.raises(PinCredentialError):
            PinCredential.set_for(operator, "abcd")

    @override_settings(DOORMAN={"PIN_DIGITS_ONLY": False, "PIN_MIN_LENGTH": 4})
    def test_policy_allows_alphanumeric_when_configured(self, operator):
        cred = PinCredential.set_for(operator, "ab12")
        assert cred.verify("ab12") is True
