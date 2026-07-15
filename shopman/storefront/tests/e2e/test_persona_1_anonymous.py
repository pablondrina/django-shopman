"""Persona 1 — Anonymous first-timer.

Discovers the shop with no account, browses the catalogue, fills a bag, logs in
by phone OTP at checkout, pays with PIX and follows the order. The order is born
from an anonymous session; the customer identity is materialised at/after commit.

Everything runs through the real ``web`` channel config (optimistic auto-confirm,
PIX paid after the store confirms).
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from shopman.orderman.models import Order

from . import _journey as J

pytestmark = pytest.mark.django_db

# pytest-django forces settings.DEBUG=False, which disables the local "simulate
# payment" action. Staging enables it via this flag; the digital-payment
# journeys opt in the same way so the mock gateway confirmation is reachable.
allow_mock_payment = override_settings(SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=True)

SKU = "PAO-FRANCES"


def _seed(stock_qty=10):
    J.seed_shop()
    J.seed_web_channel()
    collection = J.seed_collection()
    J.seed_product(SKU, "Pão Francês", 90, collection=collection, stock_qty=stock_qty)


# ── happy path ───────────────────────────────────────────────────────────────


@allow_mock_payment
def test_full_journey_browse_cart_otp_pix_track(client, django_capture_on_commit_callbacks):
    _seed(stock_qty=10)

    # 1. Discover the shop — anonymous session works, cart is empty.
    status, home = J.get_json(client, "/api/v1/storefront/home/")
    assert status == 200
    assert home["cart"]["is_empty"] is True

    # 2. Browse the catalogue — the product is listed and addable.
    status, menu = J.get_json(client, "/api/v1/storefront/menu/")
    assert status == 200
    card = next(c for c in menu["catalog"]["items"] if c["sku"] == SKU)
    assert card["availability"] in {"available", "low_stock"}
    assert card["can_add_to_cart"] is True

    # Anonymous identity.
    status, session = J.get_json(client, "/api/v1/auth/session/")
    assert session["is_authenticated"] is False

    # 3. Add two to the bag.
    status, add = J.set_cart_qty(client, SKU, 2)
    assert status == 200, add
    assert add["cart"]["items_count"] == 2

    # 4. The checkout surface asks an anonymous visitor to log in first.
    status, checkout = J.get_json(client, "/api/v1/storefront/checkout/")
    assert status == 200
    assert checkout["checkout"]["is_authenticated"] is False
    assert checkout["checkout"]["requires_authentication"] is True

    # 5. Log in by phone OTP (first-timer: no prior Customer row).
    from shopman.guestman.services import customer as customer_service

    assert customer_service.get_by_phone(J.DEFAULT_PHONE) is None
    login = J.otp_login(client, J.DEFAULT_PHONE)
    assert login["status"] == 200, login
    status, session = J.get_json(client, "/api/v1/auth/session/")
    assert session["is_authenticated"] is True

    # 6. Send the order, paying with PIX.
    status, order_resp = J.checkout(client, payment_method="pix", phone=J.DEFAULT_PHONE)
    assert status == 201, order_resp
    ref = order_resp["order_ref"]

    order = Order.objects.get(ref=ref)
    assert order.status == "new"  # optimistic: not yet confirmed
    assert (order.data.get("payment") or {}).get("method") == "pix"
    # A customer is now bound to the phone.
    customer = customer_service.get_by_phone(J.DEFAULT_PHONE)
    assert customer is not None

    # 7. Follow the order — tracking is reachable for the session that placed it.
    status, tracking = J.get_tracking(client, ref)
    assert status == 200
    assert tracking["ref"] == ref

    # 8. Optimistic confirmation (operator does not cancel) → PIX becomes payable.
    J.confirm_order(order, django_capture_on_commit_callbacks)
    assert order.status == "confirmed"

    status, payment = J.get_payment(client, ref)
    assert status == 200, payment
    assert payment.get("payment") is not None, payment
    assert payment["intent_ready"] is True

    # 9. Pay (mock gateway confirmation) and confirm the order reflects payment.
    status, confirm = J.mock_confirm_payment(client, ref)
    assert status == 200, confirm

    status, tracking = J.get_tracking(client, ref)
    assert status == 200
    assert tracking["payment_confirmed"] is True, tracking


def test_full_journey_pickup_cash(client):
    """Simplest complete journey: browse → cart → cash pickup → tracking."""
    _seed(stock_qty=5)

    J.otp_login(client, J.DEFAULT_PHONE)
    status, add = J.set_cart_qty(client, SKU, 1)
    assert status == 200, add

    status, order_resp = J.checkout(client, payment_method="cash")
    assert status == 201, order_resp
    ref = order_resp["order_ref"]

    status, tracking = J.get_tracking(client, ref)
    assert status == 200
    assert tracking["ref"] == ref
    assert len(tracking["items"]) == 1


# ── error variations ─────────────────────────────────────────────────────────


def test_checkout_empty_cart_is_rejected(client):
    _seed(stock_qty=5)
    J.otp_login(client, J.DEFAULT_PHONE)

    status, body = J.checkout(client, payment_method="cash")
    assert status == 400, body
    assert "vazia" in body["detail"].lower()


def test_add_beyond_stock_is_rejected_with_rich_payload(client):
    """Product esgotado: asking for more than exists returns a 409 with the
    available quantity and a one-tap 'use N available' action."""
    _seed(stock_qty=2)

    status, body = J.set_cart_qty(client, SKU, 5)
    assert status == 409, body
    assert body["available_qty"] == 2
    assert body["items"][0]["available_qty"] == 2
    assert any(a["ref"] == "set_available_qty" for a in body["actions"])


def test_checkout_missing_phone_is_rejected(client):
    _seed(stock_qty=5)
    J.otp_login(client, J.DEFAULT_PHONE)
    J.set_cart_qty(client, SKU, 1)

    import json

    resp = client.post(
        "/api/v1/checkout/",
        data=json.dumps({"name": "Ana", "payment_method": "cash", "fulfillment_type": "pickup"}),
        content_type="application/json",
    )
    assert resp.status_code == 400, resp.content
