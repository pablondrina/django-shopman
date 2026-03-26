"""Tests for device management views (AUTH-7).

Covers:
- List devices requires authentication
- Revoke device requires ownership
- Revoke all clears cookie
- Cannot revoke another customer's device
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User
from django.test import Client
from shopman.auth.conf import auth_settings
from shopman.auth.models.device_trust import TrustedDevice
from shopman.customers.models import Customer

pytestmark = pytest.mark.django_db


def _login_as_customer(client: Client, customer) -> User:
    """Log in the Django test client as a customer via Django auth."""
    from shopman.auth.protocols.customer import AuthCustomerInfo
    from shopman.auth.services._user_bridge import get_or_create_user_for_customer

    info = AuthCustomerInfo(
        uuid=customer.uuid,
        name=customer.name,
        phone=customer.phone,
        email=getattr(customer, "email", None) or None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.auth.backends.PhoneOTPBackend")
    return user


@pytest.fixture
def other_customer(db):
    return Customer.objects.create(
        ref="CUST-OTHER",
        first_name="Maria",
        last_name="Santos",
        phone="5543999990002",
    )


@pytest.fixture
def trusted_device(customer):
    """Create a trusted device for the test customer."""
    device, raw_token = TrustedDevice.create_for_customer(
        customer_id=customer.uuid,
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120",
    )
    return device, raw_token


@pytest.fixture
def other_device(other_customer):
    """Create a trusted device for a different customer."""
    device, raw_token = TrustedDevice.create_for_customer(
        customer_id=other_customer.uuid,
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Safari/605",
    )
    return device, raw_token


# ── DeviceListView ────────────────────────────────────────────────────


class TestDeviceListView:
    def test_list_requires_auth(self, client: Client):
        resp = client.get("/auth/devices/")
        assert resp.status_code == 200
        assert "Faça login" in resp.content.decode()

    def test_list_shows_devices(self, client: Client, customer, trusted_device):
        _login_as_customer(client, customer)
        resp = client.get("/auth/devices/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Chrome" in content or "Mac" in content

    def test_list_marks_current_device(self, client: Client, customer, trusted_device):
        device, raw_token = trusted_device
        _login_as_customer(client, customer)
        # Set the device trust cookie
        client.cookies[auth_settings.DEVICE_TRUST_COOKIE_NAME] = raw_token
        resp = client.get("/auth/devices/")
        content = resp.content.decode()
        assert "Este dispositivo" in content

    def test_list_excludes_other_customer_devices(
        self, client: Client, customer, trusted_device, other_device
    ):
        _login_as_customer(client, customer)
        resp = client.get("/auth/devices/")
        content = resp.content.decode()
        # Should show customer's device but not other_customer's
        assert str(trusted_device[0].id) in content
        assert str(other_device[0].id) not in content


# ── DeviceRevokeView ─────────────────────────────────────────────────


class TestDeviceRevokeView:
    def test_revoke_requires_auth(self, client: Client, trusted_device):
        device, _ = trusted_device
        resp = client.delete(f"/auth/devices/{device.id}/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Autenticação necessária" in content

    def test_revoke_own_device(self, client: Client, customer, trusted_device):
        device, _ = trusted_device
        _login_as_customer(client, customer)
        resp = client.delete(f"/auth/devices/{device.id}/")
        assert resp.status_code == 200
        device.refresh_from_db()
        assert device.is_active is False

    def test_revoke_other_customer_device_fails(
        self, client: Client, customer, other_device
    ):
        _login_as_customer(client, customer)
        device, _ = other_device
        resp = client.delete(f"/auth/devices/{device.id}/")
        # Returns empty (not found for this customer)
        assert resp.status_code == 200
        assert resp.content == b""
        device.refresh_from_db()
        assert device.is_active is True  # Not revoked

    def test_revoke_nonexistent_device(self, client: Client, customer):
        _login_as_customer(client, customer)
        fake_id = uuid.uuid4()
        resp = client.delete(f"/auth/devices/{fake_id}/")
        assert resp.status_code == 200
        assert resp.content == b""

    def test_revoke_invalid_uuid(self, client: Client, customer):
        _login_as_customer(client, customer)
        resp = client.delete("/auth/devices/not-a-uuid/")
        # URL pattern requires uuid, so Django returns 404
        assert resp.status_code == 404


# ── DeviceRevokeAllView ──────────────────────────────────────────────


class TestDeviceRevokeAllView:
    def test_revoke_all_requires_auth(self, client: Client):
        resp = client.delete("/auth/devices/revoke-all/")
        assert resp.status_code == 200
        assert "Autenticação necessária" in resp.content.decode()

    def test_revoke_all_clears_devices(self, client: Client, customer, trusted_device):
        device, raw_token = trusted_device
        # Create a second device
        device2, _ = TrustedDevice.create_for_customer(
            customer_id=customer.uuid,
            user_agent="Mozilla/5.0 Firefox/120",
        )
        _login_as_customer(client, customer)
        client.cookies[auth_settings.DEVICE_TRUST_COOKIE_NAME] = raw_token
        resp = client.delete("/auth/devices/revoke-all/")
        assert resp.status_code == 200
        assert "revogados" in resp.content.decode()

        # Both devices should be revoked
        device.refresh_from_db()
        device2.refresh_from_db()
        assert device.is_active is False
        assert device2.is_active is False

    def test_revoke_all_clears_cookie(self, client: Client, customer, trusted_device):
        _, raw_token = trusted_device
        _login_as_customer(client, customer)
        client.cookies[auth_settings.DEVICE_TRUST_COOKIE_NAME] = raw_token
        resp = client.delete("/auth/devices/revoke-all/")
        # Cookie should be deleted in the response
        cookie_name = auth_settings.DEVICE_TRUST_COOKIE_NAME
        assert cookie_name in resp.cookies
        assert resp.cookies[cookie_name]["max-age"] == 0

    def test_revoke_all_does_not_affect_other_customer(
        self, client: Client, customer, trusted_device, other_device
    ):
        _login_as_customer(client, customer)
        client.delete("/auth/devices/revoke-all/")

        other_dev, _ = other_device
        other_dev.refresh_from_db()
        assert other_dev.is_active is True  # Not affected
