"""Tests for core auth device management views (AUTH-7).

Tests the JSON API endpoints in shopman.auth.views.devices.
"""
from __future__ import annotations

import uuid

import pytest
from django.test import RequestFactory

from shopman.auth.models.device_trust import TrustedDevice
from shopman.auth.protocols.customer import AuthCustomerInfo
from shopman.auth.views.devices import DeviceListView, DeviceRevokeView

pytestmark = pytest.mark.django_db

CUSTOMER_ID = uuid.uuid4()
OTHER_CUSTOMER_ID = uuid.uuid4()


def _make_request(method="get", customer_id=None, cookies=None):
    """Build a request with optional customer info."""
    factory = RequestFactory()
    if method == "delete":
        request = factory.delete("/")
    else:
        request = factory.get("/")

    if customer_id:
        request.customer = AuthCustomerInfo(
            uuid=customer_id,
            name="Test",
            phone="5543999990001",
            email=None,
            is_active=True,
        )
    else:
        request.customer = None

    request.COOKIES = cookies or {}
    return request


class TestDeviceListViewJSON:
    def test_unauthenticated_returns_401(self):
        request = _make_request()
        resp = DeviceListView.as_view()(request)
        assert resp.status_code == 401

    def test_list_returns_devices(self):
        device, _ = TrustedDevice.create_for_customer(
            customer_id=CUSTOMER_ID,
            user_agent="Chrome / Mac",
        )
        request = _make_request(customer_id=CUSTOMER_ID)
        resp = DeviceListView.as_view()(request)
        assert resp.status_code == 200
        import json

        data = json.loads(resp.content)
        assert len(data["devices"]) == 1
        assert data["devices"][0]["id"] == str(device.id)

    def test_list_excludes_revoked(self):
        device, _ = TrustedDevice.create_for_customer(
            customer_id=CUSTOMER_ID,
            user_agent="Chrome / Mac",
        )
        device.revoke()
        request = _make_request(customer_id=CUSTOMER_ID)
        resp = DeviceListView.as_view()(request)
        import json

        data = json.loads(resp.content)
        assert len(data["devices"]) == 0

    def test_delete_all(self):
        TrustedDevice.create_for_customer(customer_id=CUSTOMER_ID, user_agent="A")
        TrustedDevice.create_for_customer(customer_id=CUSTOMER_ID, user_agent="B")
        request = _make_request("delete", customer_id=CUSTOMER_ID)
        resp = DeviceListView.as_view()(request)
        assert resp.status_code == 200
        import json

        data = json.loads(resp.content)
        assert data["revoked"] == 2
        assert TrustedDevice.objects.filter(
            customer_id=CUSTOMER_ID, is_active=True
        ).count() == 0


class TestDeviceRevokeViewJSON:
    def test_unauthenticated_returns_401(self):
        device, _ = TrustedDevice.create_for_customer(
            customer_id=CUSTOMER_ID, user_agent="X"
        )
        request = _make_request("delete")
        resp = DeviceRevokeView.as_view()(request, device_id=device.id)
        assert resp.status_code == 401

    def test_revoke_own_device(self):
        device, _ = TrustedDevice.create_for_customer(
            customer_id=CUSTOMER_ID, user_agent="X"
        )
        request = _make_request("delete", customer_id=CUSTOMER_ID)
        resp = DeviceRevokeView.as_view()(request, device_id=device.id)
        assert resp.status_code == 200
        device.refresh_from_db()
        assert device.is_active is False

    def test_revoke_other_customer_device_returns_404(self):
        device, _ = TrustedDevice.create_for_customer(
            customer_id=OTHER_CUSTOMER_ID, user_agent="X"
        )
        request = _make_request("delete", customer_id=CUSTOMER_ID)
        resp = DeviceRevokeView.as_view()(request, device_id=device.id)
        assert resp.status_code == 404
        device.refresh_from_db()
        assert device.is_active is True

    def test_revoke_invalid_uuid_returns_400(self):
        request = _make_request("delete", customer_id=CUSTOMER_ID)
        resp = DeviceRevokeView.as_view()(request, device_id="not-a-uuid")
        assert resp.status_code == 400
