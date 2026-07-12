"""IP do registro de consentimento (LGPD) não pode ser forjável.

O leftmost do X-Forwarded-For é escrito pelo CLIENTE (spoofável); o IP
confiável é o rightmost respeitando ``TRUSTED_PROXY_DEPTH`` — resolvido pelo
helper canônico ``shopman.shop.services.auth.client_ip``.
"""

from __future__ import annotations

import json

import pytest
from django.test import Client
from shopman.guestman.models import Customer

pytestmark = pytest.mark.django_db


def _login_as_customer(client: Client, customer: Customer):
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    info = AuthCustomerInfo(
        uuid=customer.uuid,
        name=customer.name,
        phone=customer.phone,
        email=getattr(customer, "email", None) or None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")
    return user


def test_consent_ip_ignores_spoofed_leftmost_xff(client: Client, monkeypatch):
    customer = Customer.objects.create(
        ref="CUS-IP-01",
        first_name="Ana",
        last_name="Silva",
        phone="+5543999990101",
    )
    _login_as_customer(client, customer)

    from shopman.storefront.api import account as account_api

    captured: dict = {}

    def fake_toggle(ref, channel, *, ip_address):
        captured["ip_address"] = ip_address
        return object()

    monkeypatch.setattr(account_api.account_service, "toggle_notification_consent", fake_toggle)
    monkeypatch.setattr(account_api, "present_notification_prefs", lambda _prefs: [])

    response = client.post(
        "/api/v1/account/preferences/notifications/",
        data=json.dumps({"channel": "whatsapp"}),
        content_type="application/json",
        # Cliente forja o leftmost; o proxy confiável anexa o IP real à direita.
        HTTP_X_FORWARDED_FOR="6.6.6.6, 203.0.113.9",
    )

    assert response.status_code == 200
    assert captured["ip_address"] == "203.0.113.9"
