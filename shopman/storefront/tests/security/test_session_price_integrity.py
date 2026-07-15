"""Categories 2 & 3 — session manipulation and price integrity.

Category 2 (session manipulation):
- The cart lives in the server-side Orderman session, keyed by a value stored in
  the Django session cookie. No request parameter may switch or read another
  visitor's cart (no session fixation, no cart IDOR).
- Client-supplied fields the server must not trust: fulfillment_type is
  whitelisted; loyalty redemption is resolved server-side (an anonymous caller
  cannot inject a redeem amount).

Category 3 (price integrity):
- The price charged at commit is the CURRENT catalog price, not the price
  captured when the item entered the cart (internal pricing re-resolves).
- A client-supplied ``expected_total_q`` lower than the real total aborts the
  commit — it can never make the server charge less (no underpay).
- A discount can never exceed the merchandise value: line totals and the order
  total floor at zero, never negative.
"""
from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.offerman.models import ListingItem
from shopman.orderman.models import Order, Session

from shopman.shop.services import checkout as checkout_service
from shopman.shop.services import sessions as session_service

pytestmark = pytest.mark.django_db


def _relist(product, price_q: int, *, listing_ref: str = "web") -> None:
    """Set the current catalog (listing) price for ``product`` on the channel."""
    ListingItem.objects.filter(
        listing__ref=listing_ref, product=product
    ).update(price_q=price_q, is_published=True, is_sellable=True)


# ── Category 3: price at commit is the current catalog price ────────────────


def test_commit_uses_current_catalog_price_not_add_time_price(cart_session, product):
    """Item entered the cart at R$0,90; the catalog price is then raised to
    R$1,50. The committed order must charge R$1,50 x2 = R$3,00, not the stale
    R$0,90 x2 = R$1,80."""
    client = cart_session
    session_key = client.session["cart_session_key"]

    # Sanity: cart captured the add-time price (90 x2 = 180).
    session = Session.objects.get(session_key=session_key, channel_ref="web")
    assert sum(i["line_total_q"] for i in session.items) == 180

    # Catalog price changes AFTER add-to-cart.
    _relist(product, price_q=150)

    result = checkout_service.process(
        session_key=session_key,
        channel_ref="web",
        data={"customer": {"name": "Ana", "phone": "+5543999990001"}, "fulfillment_type": "pickup"},
        idempotency_key=session_service.new_idempotency_key(),
    )
    order = Order.objects.get(ref=result.order_ref)
    assert order.total_q == 300, (
        f"price integrity: committed at {order.total_q}, expected 300 (current catalog "
        "price). A stale 180 means the cart's add-time price was charged."
    )


def test_expected_total_guard_blocks_stale_undercharge(cart_session, product):
    """If the client sends the total it saw (180) but the catalog price rose to
    150 (real total 300), the commit is REJECTED — the customer is never
    silently charged a different total, and the client cannot pin an old total
    to underpay."""
    from shopman.orderman.exceptions import ValidationError as OrderingValidationError

    client = cart_session
    session_key = client.session["cart_session_key"]
    _relist(product, price_q=150)

    with pytest.raises(OrderingValidationError) as exc:
        checkout_service.process(
            session_key=session_key,
            channel_ref="web",
            data={"customer": {"name": "Ana", "phone": "+5543999990001"}, "fulfillment_type": "pickup"},
            idempotency_key=session_service.new_idempotency_key(),
            expected_total_q=180,  # what the client saw — now stale
        )
    assert exc.value.code == "total_changed"
    # No order was created.
    assert not Order.objects.filter(session_key=session_key).exists()


def test_fixed_discount_cannot_exceed_merchandise_value(channel, product):
    """A fixed coupon worth far more than the cart cannot drive the order total
    negative — it floors at zero (no free money / no negative charge)."""
    from shopman.storefront.models import Coupon, Promotion

    # Cheap cart: 1 unit @ R$0,80.
    session = session_service.create_session("web")
    session_service.modify_session(
        session_key=session.session_key,
        channel_ref="web",
        ops=[
            {"op": "add_line", "sku": product.sku, "name": product.name, "qty": 1, "unit_price_q": 80},
            {"op": "set_data", "path": "customer", "value": {"name": "Ana", "phone": "+5543999990001"}},
            {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
        ],
    )
    now = timezone.now()
    promo = Promotion.objects.create(
        name="Vale gigante",
        type=Promotion.FIXED,
        value=100000,  # R$1.000,00 fixed — dwarfs the R$0,80 cart
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
    )
    Coupon.objects.create(code="GIGANTE", promotion=promo, max_uses=0)

    session_service.modify_session(
        session_key=session.session_key,
        channel_ref="web",
        ops=[{"op": "set_data", "path": "coupon_code", "value": "GIGANTE"}],
    )
    result = checkout_service.process(
        session_key=session.session_key,
        channel_ref="web",
        data={"customer": {"name": "Ana", "phone": "+5543999990001"}, "fulfillment_type": "pickup"},
        idempotency_key=session_service.new_idempotency_key(),
    )
    order = Order.objects.get(ref=result.order_ref)
    assert order.total_q >= 0, f"negative order total: {order.total_q}"
    assert order.total_q == 0, (
        f"discount exceeded merchandise value: total {order.total_q}, expected floor 0"
    )


# ── Category 2: cart isolation / session fixation ──────────────────────────


def test_carts_are_isolated_between_sessions(cart_session):
    """Client A has an item in the cart; a fresh Client B sees an empty cart —
    carts do not bleed across Django sessions."""
    from django.test import Client

    resp_a = cart_session.get("/api/v1/storefront/cart/")
    assert resp_a.json()["cart"]["items_count"] == 2

    other = Client()
    resp_b = other.get("/api/v1/storefront/cart/")
    assert resp_b.json()["cart"]["items_count"] == 0


def test_cart_session_key_not_switchable_by_request_param(cart_session):
    """A victim's cart cannot be hijacked by supplying their cart_session_key as
    a query/body parameter — the server keys the cart off the signed Django
    session cookie only."""
    from django.test import Client

    victim_key = cart_session.session["cart_session_key"]
    attacker = Client()

    via_query = attacker.get(f"/api/v1/storefront/cart/?session_key={victim_key}")
    via_query2 = attacker.get(f"/api/v1/storefront/cart/?cart_session_key={victim_key}")
    assert via_query.json()["cart"]["items_count"] == 0
    assert via_query2.json()["cart"]["items_count"] == 0


def test_checkout_draft_only_persists_whitelisted_fields(cart_session):
    """CheckoutDraftView must ignore junk keys and coerce an invalid
    fulfillment_type to 'pickup' — a client cannot smuggle arbitrary keys into
    session.data via the draft endpoint."""
    client = cart_session
    session_key = client.session["cart_session_key"]

    resp = client.patch(
        "/api/v1/checkout/draft/",
        data=json.dumps({
            "fulfillment_type": "teleport",  # invalid → coerced to pickup
            "delivery_address_structured": {
                "formatted_address": "Rua X 1",
                "evil_key": "DROP TABLE",       # not whitelisted
                "unit_price_q": 1,              # not whitelisted
            },
            "discount_q": 99999,               # top-level junk
            "coupon_code": "FREE",             # top-level junk
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200

    session = Session.objects.get(session_key=session_key, channel_ref="web")
    # Junk keys never land in session.data anywhere.
    blob = json.dumps(session.data)
    assert "evil_key" not in blob
    assert "DROP TABLE" not in blob
    assert "FREE" not in blob
    # fulfillment_type, if stored, is the coerced safe value.
    ft = (session.data or {}).get("fulfillment_type")
    assert ft in (None, "pickup")


def test_anonymous_cannot_inject_loyalty_redemption(cart_session):
    """An anonymous visitor toggling loyalty on cannot inject a redeem amount;
    the server resolves the balance itself (0 for an anonymous caller), so no
    discount is applied."""
    client = cart_session
    resp = client.patch(
        "/api/v1/checkout/loyalty/",
        data=json.dumps({"enabled": True, "redeem_q": 99999, "points_balance": 99999}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    # Subtotal unchanged — no phantom loyalty discount for an anonymous caller.
    assert resp.json()["cart"]["subtotal_q"] == 180
