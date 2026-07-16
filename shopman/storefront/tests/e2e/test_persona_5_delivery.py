"""Persona 5 — Delivery with a covered address.

Orders for delivery to an address inside a covered zone. The delivery draft
previews the zone fee before commit; the fee becomes a real order line and enters
the total. Addresses outside the covered area are refused at commit.
"""

from __future__ import annotations

import json

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from . import _journey as J

pytestmark = pytest.mark.django_db

SKU = "PAO-ENTREGA"
FEE_Q = 600
COVERED = {"postal_code": "86050-270", "neighborhood": "Centro"}


def _seed(*, exclude_prefix=None):
    shop = J.seed_shop()
    J.seed_web_channel()
    collection = J.seed_collection()
    J.seed_product(SKU, "Pão", 2500, collection=collection, stock_qty=20)
    J.seed_delivery_zone(shop, match_value="860", fee_q=FEE_Q, name="Londrina 860")
    if exclude_prefix:
        J.seed_delivery_zone(
            shop, match_value=exclude_prefix, fee_q=0, mode="exclude", name="Fora de área"
        )
    return shop


def _checkout_delivery(client, structured, **overrides):
    payload = {
        "name": "Ana Silva",
        "phone": J.DEFAULT_PHONE,
        "fulfillment_type": "delivery",
        "payment_method": "cash",
        "delivery_date": timezone.localdate().isoformat(),
        "delivery_address": "Rua das Flores, 123",
        "delivery_address_structured": structured,
    }
    payload.update(overrides)
    resp = client.post("/api/v1/checkout/", data=json.dumps(payload), content_type="application/json")
    return resp.status_code, (resp.json() if resp.content else None)


# ── happy path ───────────────────────────────────────────────────────────────


def test_full_delivery_journey_zone_fee_in_total(client):
    _seed()
    J.otp_login(client)
    J.set_cart_qty(client, SKU, 1)  # R$25,00

    # Draft previews the zone fee before commit.
    status, draft = J.checkout_draft(client, fulfillment_type="delivery", structured=COVERED)
    assert status == 200, draft
    cart = draft["cart"]
    assert cart["delivery_fee_q"] == FEE_Q
    assert cart["grand_total_q"] == 2500 + FEE_Q

    # Commit — the fee is a real order line and enters the total.
    status, resp = _checkout_delivery(client, COVERED)
    assert status == 201, resp

    order = Order.objects.get(ref=resp["order_ref"])
    assert order.data.get("fulfillment_type") == "delivery"
    assert order.data.get("delivery_fee_q") == FEE_Q
    assert order.total_q == 2500 + FEE_Q

    status, tracking = J.get_tracking(client, resp["order_ref"])
    assert status == 200
    assert tracking["is_delivery"] is True


# ── error variations ─────────────────────────────────────────────────────────


def test_address_outside_area_is_refused_at_commit(client):
    """An address matched by an ``exclude`` zone blocks the order."""
    _seed(exclude_prefix="862")
    J.otp_login(client)
    J.set_cart_qty(client, SKU, 1)

    status, body = _checkout_delivery(
        client, {"postal_code": "86200-000", "neighborhood": "Cambé"}
    )
    assert status == 400, body
    assert "delivery_address" in {body.get("field"), *(body.get("errors") or {})}


def test_delivery_without_address_is_rejected(client):
    _seed()
    J.otp_login(client)
    J.set_cart_qty(client, SKU, 1)

    resp = client.post(
        "/api/v1/checkout/",
        data=json.dumps({
            "name": "Ana", "phone": J.DEFAULT_PHONE, "fulfillment_type": "delivery",
            "payment_method": "cash", "delivery_date": timezone.localdate().isoformat(),
        }),
        content_type="application/json",
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["field"] == "delivery_address"


def test_delivery_without_date_is_rejected(client):
    _seed()
    J.otp_login(client)
    J.set_cart_qty(client, SKU, 1)

    resp = client.post(
        "/api/v1/checkout/",
        data=json.dumps({
            "name": "Ana", "phone": J.DEFAULT_PHONE, "fulfillment_type": "delivery",
            "payment_method": "cash", "delivery_address": "Rua X, 1",
            "delivery_address_structured": COVERED,
        }),
        content_type="application/json",
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["field"] == "delivery_date"
