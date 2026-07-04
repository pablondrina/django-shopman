"""GET /api/v1/tracking/<ref>/events/ — SSE push authorization gate.

The stream itself (fan-out of ``order-<ref>`` events) is exercised by the
channel-manager unit tests in shop/tests/test_eventstream_permissions.py; here
we assert the HTTP contract the Nuxt client depends on: owners/staff get a live
``text/event-stream`` (200), everyone else gets a uniform 404 so their browser
EventSource fails once and stays on the poll fallback.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.urls import resolve
from shopman.doorman.models import CustomerUser
from shopman.guestman.models import Customer
from shopman.orderman.models import Order

from shopman.storefront.api.tracking import order_events_view

pytestmark = pytest.mark.django_db


@pytest.fixture
def order(db):
    customer = Customer.objects.create(
        ref="CUST-EV-1", first_name="Ana", phone="5543999990001"
    )
    order = Order.objects.create(
        ref="ORD-EV-1",
        channel_ref="web",
        status="new",
        total_q=1000,
        handle_type="phone",
        handle_ref=customer.phone,
        data={"customer_ref": customer.ref},
    )
    return customer, order


def test_events_route_is_wired_to_the_authorizing_wrapper():
    match = resolve("/api/v1/tracking/ORD-EV-1/events/")
    assert match.func is order_events_view
    assert match.kwargs == {"ref": "ORD-EV-1"}


def test_guest_without_login_is_denied(client, order):
    _, o = order
    resp = client.get(f"/api/v1/tracking/{o.ref}/events/")
    assert resp.status_code == 404


def test_non_owner_is_denied(client, order):
    _, o = order
    other = User.objects.create_user(username="other")
    client.force_login(other)
    resp = client.get(f"/api/v1/tracking/{o.ref}/events/")
    assert resp.status_code == 404


def test_missing_ref_is_denied_with_the_same_status(client):
    # Uniform 404 whether the ref is missing or simply not the caller's — never
    # leaks whether a ref exists.
    resp = client.get("/api/v1/tracking/DOES-NOT-EXIST/events/")
    assert resp.status_code == 404


def test_owner_gets_a_live_event_stream(client, order):
    customer, o = order
    user = User.objects.create_user(username="ana")
    CustomerUser.objects.create(user=user, customer_id=customer.uuid)
    client.force_login(user)

    resp = client.get(f"/api/v1/tracking/{o.ref}/events/")

    assert resp.status_code == 200
    assert resp["content-type"].startswith("text/event-stream")
    # Never iterate streaming_content — it is an open SSE generator that would
    # block the test. The 200 + content-type is the contract the BFF needs.
    resp.close()


def test_staff_can_read_any_order_stream(client, order):
    _, o = order
    staff = User.objects.create_user(username="ops", is_staff=True)
    client.force_login(staff)

    resp = client.get(f"/api/v1/tracking/{o.ref}/events/")

    assert resp.status_code == 200
    assert resp["content-type"].startswith("text/event-stream")
    resp.close()
