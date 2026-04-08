"""Tests for AUTH-6B: Verify Django auth is set by all login flows.

After cutover: session keys removed, only Django auth remains.
"""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client

pytestmark = pytest.mark.django_db


class TestVerifyCodeAuth:
    """VerifyCodeView sets request.user via Django auth."""

    def test_verify_code_sets_django_user(self, client: Client, customer):
        """request.user is authenticated after OTP verification."""
        from shopman.doorman.models import VerificationCode
        from shopman.doorman.models.verification_code import generate_raw_code

        raw_code, hmac_digest = generate_raw_code()
        VerificationCode.objects.create(
            code_hash=hmac_digest,
            target_value=customer.phone,
            purpose="login",
            status="sent",
        )

        client.post("/checkout/verify-code/", {
            "phone": customer.phone,
            "code": raw_code,
        })

        # User ID should be in the session (Django auth)
        user_id = client.session.get("_auth_user_id")
        assert user_id is not None

        # User should exist and be linked to customer
        user = User.objects.get(pk=user_id)
        assert user.is_active

        from shopman.doorman.models import CustomerUser
        link = CustomerUser.objects.get(user=user)
        assert link.customer_id == customer.uuid


class TestDeviceCheckAuth:
    """DeviceCheckLoginView sets request.user via Django auth."""

    def _trust_device(self, client: Client, customer):
        """Simulate trusting a device by creating a device and setting cookie."""
        from shopman.doorman.models.device_trust import TrustedDevice

        device, raw_token = TrustedDevice.create_for_customer(
            customer_id=customer.uuid,
        )
        from shopman.doorman.conf import auth_settings
        client.cookies[auth_settings.DEVICE_TRUST_COOKIE_NAME] = raw_token

    def test_device_check_sets_django_user(self, client: Client, customer):
        """request.user is authenticated after device trust login."""
        self._trust_device(client, customer)
        client.post("/auth/device-check/", {"phone": customer.phone})

        # Django user should be in session
        user_id = client.session.get("_auth_user_id")
        assert user_id is not None

        user = User.objects.get(pk=user_id)
        from shopman.doorman.models import CustomerUser
        link = CustomerUser.objects.get(user=user)
        assert link.customer_id == customer.uuid
