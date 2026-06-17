"""Security tests for the order API surface (headless).

Order access is enforced by the API the BFF consumes (`get_accessible_order`):
a session may only read an order it owns (via login match or a magic-link grant).
Ref-guessing by an anonymous attacker must 404.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone
from shopman.doorman.models import AccessLink
from shopman.guestman.models import Customer
from shopman.orderman.models import Order

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


def test_tracking_api_ref_guess_returns_404(order):
    attacker = Client()

    response = attacker.get(f"/api/v1/tracking/{order.ref}/")

    assert response.status_code == 404


def test_tracking_api_allows_session_order_access(client, order):
    response = client.get(f"/api/v1/tracking/{order.ref}/")

    assert response.status_code == 200
    assert response.json()["ref"] == order.ref


def test_payment_api_ref_guess_returns_404(order_with_payment):
    attacker = Client()

    response = attacker.get(f"/api/v1/payment/{order_with_payment.ref}/")

    assert response.status_code == 404


def test_reorder_api_ref_guess_returns_404(order_items):
    attacker = Client()

    response = attacker.post(f"/api/v1/orders/{order_items.ref}/reorder/")

    assert response.status_code == 404


def test_authenticated_matching_customer_can_open_tracking(order, customer):
    order.data = {"customer_ref": customer.ref}
    order.save(update_fields=["data", "updated_at"])
    fresh_browser = Client()
    _login_as_customer(fresh_browser, customer)

    response = fresh_browser.get(f"/api/v1/tracking/{order.ref}/")

    assert response.status_code == 200
    assert response.json()["ref"] == order.ref


def test_access_link_metadata_grants_session_order_access(client, channel, customer):
    order = Order.objects.create(
        ref="ORD-LINK-001",
        channel_ref=channel.ref,
        status="new",
        total_q=1000,
        handle_type="marketplace_order",
        handle_ref="",
        data={},
    )
    _link, raw_token = AccessLink.create_with_token(
        customer_id=customer.uuid,
        audience=AccessLink.Audience.WEB_GENERAL,
        source=AccessLink.Source.INTERNAL,
        expires_at=timezone.now() + timedelta(minutes=5),
        metadata={"order_ref": order.ref},
    )

    entry = client.post("/api/v1/auth/access/", {"token": raw_token})

    assert entry.status_code == 200
    assert entry.json()["redirect"] == f"/tracking/{order.ref}"
    # The magic link binds order access to the session (store host).
    assert order.ref in client.session.get("shopman_order_access_refs", [])
