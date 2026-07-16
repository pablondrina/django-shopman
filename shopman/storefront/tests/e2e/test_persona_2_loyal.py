"""Persona 2 — Loyal customer.

A returning, phone-authenticated customer with order history, a loyalty balance,
a saved default address and favourites. Reorders a past order, redeems points and
pays. Covers redeem/debit, favourites, saved address, reorder and coupons.

Two customer-facing defects were discovered while writing this persona and are
pinned as strict ``xfail`` so the suite flags them the moment they are fixed:

  * Group-scoped (loyalty/staff) coupons are ACCEPTED at apply-time but strike a
    zero discount — the eligibility gate reads ``customer.group`` directly while
    the discount modifier reads it from a pricing context the storefront never
    populates. See ``test_group_coupon_should_discount_for_member``.
  * A card checkout on the ``web`` channel raises HTTP 400 ``sealed_field_modified``
    (post_commit + card initiates payment inside the on-commit dispatch on the
    sealed order instance). See ``test_card_checkout_on_web_is_broken``.
"""

from __future__ import annotations

import json

import pytest
from django.test import override_settings
from django.utils import timezone
from shopman.guestman.models import Customer, CustomerGroup
from shopman.orderman.models import Order

from . import _journey as J

pytestmark = pytest.mark.django_db

allow_mock_payment = override_settings(SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=True)

CROISSANT = "CROIS-01"
PAO = "PAO-01"


def _seed_catalog():
    J.seed_shop(latitude=-23.3045, longitude=-51.1628)
    J.seed_web_channel()
    collection = J.seed_collection()
    J.seed_product(CROISSANT, "Croissant", 750, collection=collection, stock_qty=20)
    J.seed_product(PAO, "Pão", 500, collection=collection, sort_order=2, stock_qty=20)


def _loyal_customer(group_ref="fieis"):
    group = CustomerGroup.objects.create(ref=group_ref, name="Fiéis", priority=5)
    return Customer.objects.create(
        ref="CUST-LOYAL-1",
        first_name="Maria",
        last_name="Fiel",
        phone=J.DEFAULT_PHONE,
        email="maria@example.com",
        group=group,
    )


# ── happy path ───────────────────────────────────────────────────────────────


@allow_mock_payment
def test_full_journey_reorder_redeem_pix(client, django_capture_on_commit_callbacks):
    _seed_catalog()
    customer = _loyal_customer()
    J.give_loyalty(customer, 1000)  # R$10,00 redeemable
    J.seed_address(customer, is_default=True)
    J.add_favorite(customer, CROISSANT)
    past = J.seed_past_order(
        customer,
        ref="ORD-HIST-1",
        items=[{"sku": CROISSANT, "name": "Croissant", "qty": 2, "unit_price_q": 750, "line_total_q": 1500}],
    )

    J.authenticate(client, customer)

    # Identity + history surfaces.
    _, session = J.get_json(client, "/api/v1/auth/session/")
    assert session["is_authenticated"] is True
    assert session["customer_name"].startswith("Maria")

    # Favourites are accessible and resolve to a real product card.
    status, favs = J.get_json(client, "/api/v1/account/favorites/")
    assert status == 200, favs
    assert any(item["sku"] == CROISSANT for item in favs["items"])

    # Saved default address is present.
    status, addresses = J.get_json(client, "/api/v1/account/addresses/")
    assert status == 200
    default_addr = next(a for a in addresses if a["is_default"])
    assert default_addr["city"] == "Londrina"

    # Reorder the past order — empty cart, so it fills directly.
    status, ro = J.reorder(client, past.ref)
    assert status == 200, ro
    assert ro["cart"]["items_count"] == 2

    # Redeem loyalty points at checkout (pickup + PIX). The on-commit pipeline is
    # executed so the redemption directive actually debits the points ledger.
    status, order_resp = J.checkout_committed(
        client,
        django_capture_on_commit_callbacks,
        name="Maria Fiel",
        payment_method="pix",
        use_loyalty=True,
    )
    assert status == 201, order_resp
    ref = order_resp["order_ref"]

    order = Order.objects.get(ref=ref)
    loyalty = order.data.get("loyalty") or {}
    assert loyalty.get("applied_discount_q", 0) > 0, order.data
    assert order.total_q < 1500  # subtotal 2×750, reduced by the redemption

    # Points were debited by exactly the discount granted.
    from shopman.guestman.contrib.loyalty import LoyaltyService

    assert LoyaltyService.get_balance(customer.ref) == 1000 - loyalty["applied_discount_q"]

    # Optimistic confirmation → PIX becomes payable → pay → tracking reflects it.
    J.confirm_order(order, django_capture_on_commit_callbacks)
    status, payment = J.get_payment(client, ref)
    assert status == 200 and payment["payment"] is not None, payment
    status, _ = J.mock_confirm_payment(client, ref)
    assert status == 200
    _, tracking = J.get_tracking(client, ref)
    assert tracking["payment_confirmed"] is True


def test_open_loyalty_coupon_applies_discount(client):
    """A non-gated loyalty coupon strikes a concrete discount into the cart."""
    _seed_catalog()
    customer = _loyal_customer()
    J.authenticate(client, customer)
    J.seed_coupon("BEMVINDO", kind="fixed", value=300, name="Boas-vindas")

    J.set_cart_qty(client, CROISSANT, 1)  # R$7,50
    status, body = J.apply_coupon(client, "bemvindo")  # case-insensitive
    assert status == 200, body
    cart = body["cart"]
    assert cart["discount_total_q"] == 300
    assert cart["coupon_code"] == "BEMVINDO"
    assert cart["coupon_discount_q"] == 300
    assert cart["has_discount"] is True


def test_group_gated_coupon_is_accepted_for_member(client):
    """A coupon scoped to the loyalty group passes the eligibility gate."""
    _seed_catalog()
    customer = _loyal_customer(group_ref="fieis")
    J.authenticate(client, customer)
    J.seed_coupon("FIEL10", kind="percent", value=10, customer_segments=["fieis"], name="Fidelidade")

    J.set_cart_qty(client, CROISSANT, 1)
    status, body = J.apply_coupon(client, "FIEL10")
    assert status == 200, body
    assert body["cart"]["coupon_code"] == "FIEL10"


# ── discovered defects (pinned expectations) ─────────────────────────────────


@pytest.mark.xfail(
    strict=True,
    reason="FINDING: group-scoped coupon accepted but discounts nothing — the "
    "storefront pricing context never carries the authenticated customer's group, "
    "so DiscountModifier._matches rejects the segment-gated promo.",
)
def test_group_coupon_should_discount_for_member(client):
    _seed_catalog()
    customer = _loyal_customer(group_ref="fieis")
    J.authenticate(client, customer)
    J.seed_coupon("FIEL10", kind="percent", value=10, customer_segments=["fieis"], name="Fidelidade")

    J.set_cart_qty(client, CROISSANT, 1)  # R$7,50
    _, body = J.apply_coupon(client, "FIEL10")
    # A 10% loyalty coupon for an eligible member should take R$0,75 off.
    assert body["cart"]["coupon_discount_q"] == 75


@pytest.mark.django_db(transaction=True)  # real commit so on-commit dispatch fires in-request
def test_card_checkout_on_web_succeeds(client):
    # Regressão do achado da persona 2: o card no web (post_commit) iniciava o
    # pagamento no dispatch on-commit sobre o pedido já selado e levantava
    # ImmutabilityError (HTTP 400 sealed_field_modified), deixando um pedido órfão.
    # Corrigido em #94 (deep-copy do snapshot selado no commit) — agora retorna 201.
    _seed_catalog()
    J.otp_login(client, J.DEFAULT_PHONE)
    J.set_cart_qty(client, CROISSANT, 1)

    resp = client.post(
        "/api/v1/checkout/",
        data=json.dumps({
            "name": "Maria", "phone": J.DEFAULT_PHONE, "fulfillment_type": "pickup",
            "payment_method": "card", "delivery_time_slot": J.last_pickup_slot(),
            "delivery_date": timezone.localdate().isoformat(),
        }),
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.json()


# ── error variations ─────────────────────────────────────────────────────────


def test_group_gated_coupon_rejected_for_anonymous(client):
    """A group-scoped coupon is refused when there is no eligible customer."""
    _seed_catalog()
    J.seed_coupon("FIEL10", kind="percent", value=10, customer_segments=["fieis"], name="Fidelidade")

    J.set_cart_qty(client, CROISSANT, 1)  # anonymous session
    status, body = J.apply_coupon(client, "FIEL10")
    assert status == 400, body
    assert body["error_code"] == "coupon_not_eligible"


def test_reorder_conflict_requires_mode_when_cart_has_items(client):
    _seed_catalog()
    customer = _loyal_customer()
    past = J.seed_past_order(
        customer,
        ref="ORD-HIST-2",
        items=[{"sku": CROISSANT, "name": "Croissant", "qty": 1, "unit_price_q": 750, "line_total_q": 750}],
    )
    J.authenticate(client, customer)
    J.set_cart_qty(client, PAO, 1)  # cart already has something

    status, body = J.reorder(client, past.ref)  # no mode
    assert status == 409, body

    status, body = J.reorder(client, past.ref, mode="append")
    assert status == 200, body
    assert body["cart"]["items_count"] == 2


def test_exhausted_coupon_is_rejected(client):
    _seed_catalog()
    customer = _loyal_customer()
    J.authenticate(client, customer)
    coupon = J.seed_coupon("USADO", kind="fixed", value=200, max_uses=1, name="Esgotado")
    coupon.uses_count = 1
    coupon.save(update_fields=["uses_count"])

    J.set_cart_qty(client, CROISSANT, 1)
    status, body = J.apply_coupon(client, "USADO")
    assert status == 400, body
    assert body["error_code"] == "coupon_exhausted"
