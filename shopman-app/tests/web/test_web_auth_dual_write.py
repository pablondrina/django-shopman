"""Tests for AUTH-6A: Dual Write — verify login() is called alongside session keys.

Zero behavior change: existing session-based auth continues working.
New: request.user.is_authenticated is also True after OTP/device-trust login.
"""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client

from channels.web.views.auth import (
    SESSION_CUSTOMER_UUID,
    SESSION_VERIFIED,
    SESSION_VERIFIED_PHONE,
)

pytestmark = pytest.mark.django_db


class TestVerifyCodeDualWrite:
    """VerifyCodeView sets both session keys AND request.user."""

    def test_verify_code_sets_session_keys(self, client: Client, customer):
        """Session keys still set after OTP verification (backward compat)."""
        from shopman.auth.models import VerificationCode
        from shopman.auth.models.verification_code import generate_raw_code

        raw_code, hmac_digest = generate_raw_code()
        VerificationCode.objects.create(
            code_hash=hmac_digest,
            target_value=customer.phone,
            purpose="login",
            status="sent",
        )

        resp = client.post("/checkout/verify-code/", {
            "phone": customer.phone,
            "code": raw_code,
        })
        assert resp.status_code == 200

        session = client.session
        assert session.get(SESSION_CUSTOMER_UUID) == str(customer.uuid)
        assert session.get(SESSION_VERIFIED) is True
        assert session.get(SESSION_VERIFIED_PHONE) == customer.phone

    def test_verify_code_sets_django_user(self, client: Client, customer):
        """request.user is authenticated after OTP verification."""
        from shopman.auth.models import VerificationCode
        from shopman.auth.models.verification_code import generate_raw_code

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

        from shopman.auth.models import CustomerUser
        link = CustomerUser.objects.get(user=user)
        assert link.customer_id == customer.uuid


class TestDeviceCheckDualWrite:
    """DeviceCheckLoginView sets both session keys AND request.user."""

    def _trust_device(self, client: Client, customer):
        """Simulate trusting a device by creating a device and setting cookie."""
        from shopman.auth.models.device_trust import TrustedDevice

        device, raw_token = TrustedDevice.create_for_customer(
            customer_id=customer.uuid,
        )
        from shopman.auth.conf import auth_settings
        client.cookies[auth_settings.DEVICE_TRUST_COOKIE_NAME] = raw_token

    def test_device_check_sets_session_keys(self, client: Client, customer):
        """Session keys set after device trust login."""
        self._trust_device(client, customer)
        resp = client.post("/auth/device-check/", {"phone": customer.phone})
        data = resp.json()
        assert data["trusted"] is True

        session = client.session
        assert session.get(SESSION_CUSTOMER_UUID) == str(customer.uuid)
        assert session.get(SESSION_VERIFIED) is True

    def test_device_check_sets_django_user(self, client: Client, customer):
        """request.user is authenticated after device trust login."""
        self._trust_device(client, customer)
        client.post("/auth/device-check/", {"phone": customer.phone})

        # Django user should be in session
        user_id = client.session.get("_auth_user_id")
        assert user_id is not None

        user = User.objects.get(pk=user_id)
        from shopman.auth.models import CustomerUser
        link = CustomerUser.objects.get(user=user)
        assert link.customer_id == customer.uuid
