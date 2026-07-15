"""Persona 6 — Bundle + automatic promotion.

A bag with a combo (bundle) and an individually-promoted item. Bundle
availability is the scarcest component; an automatic (coupon-less) promotion
strikes the eligible item's price in the catalogue; a manual coupon does not
stack on top of the automatic promotion on the same line (biggest wins).
"""

from __future__ import annotations

import pytest
from shopman.orderman.models import Order

from . import _journey as J

pytestmark = pytest.mark.django_db

COMBO = "COMBO-PETIT-DEJ"
CROISSANT = "CROISSANT"
MINI = "MINI-BAGUETE"
MUFFIN = "MUFFIN"


def _seed(*, croissant_stock=20, mini_stock=20):
    J.seed_shop()
    J.seed_web_channel()
    collection = J.seed_collection()
    listing = J.seed_listing()
    crois = J.seed_product(CROISSANT, "Croissant", 700, listing=listing, collection=collection, stock_qty=croissant_stock)
    mini = J.seed_product(MINI, "Mini baguete", 500, listing=listing, collection=collection, sort_order=2, stock_qty=mini_stock)
    J.seed_bundle(
        COMBO, "Combo Petit Déjeuner", 1900,
        components=[(crois, 1), (mini, 1)],
        listing=listing, collection=collection, sort_order=3,
    )
    return collection, listing


def _card(client, sku):
    _, menu = J.get_json(client, "/api/v1/storefront/menu/")
    return next(c for c in menu["catalog"]["items"] if c["sku"] == sku)


# ── bundle availability = min(components) ─────────────────────────────────────


def test_bundle_availability_follows_scarcest_component(client):
    _seed(croissant_stock=3, mini_stock=20)  # croissant is the bottleneck
    card = _card(client, COMBO)
    assert card["available_qty"] == 3
    assert card["availability"] in {"low_stock", "available"}
    assert card["can_add_to_cart"] is True


def test_bundle_unavailable_when_a_component_is_out_of_stock(client):
    _seed(croissant_stock=None, mini_stock=20)  # croissant has no stock at all
    card = _card(client, COMBO)
    assert card["availability"] == "unavailable"
    assert card["can_add_to_cart"] is False

    # And the cart refuses to add it.
    status, body = J.set_cart_qty(client, COMBO, 1)
    assert status == 409, body


# ── automatic promotion in the catalogue ─────────────────────────────────────


def test_automatic_promotion_strikes_eligible_item_price(client):
    collection, listing = _seed()
    J.seed_product(MUFFIN, "Muffin", 1000, listing=listing, collection=collection, sort_order=4, stock_qty=20)
    J.seed_promotion(name="Semana Doce", kind="percent", value=30, skus=[MUFFIN])  # no coupon → automatic

    card = _card(client, MUFFIN)
    assert card["has_promotion"] is True
    assert card["base_price_q"] == 700  # 30% off R$10,00
    assert card["original_price_display"]


# ── full journey: bundle + promoted item ─────────────────────────────────────


def test_journey_bundle_plus_promoted_item(client):
    collection, listing = _seed()
    J.seed_product(MUFFIN, "Muffin", 1000, listing=listing, collection=collection, sort_order=4, stock_qty=20)
    J.seed_promotion(name="Semana Doce", kind="percent", value=30, skus=[MUFFIN])
    J.otp_login(client)

    assert J.set_cart_qty(client, COMBO, 1)[0] == 200
    assert J.set_cart_qty(client, MUFFIN, 1)[0] == 200

    status, resp = J.checkout(client, payment_method="cash")
    assert status == 201, resp

    order = Order.objects.get(ref=resp["order_ref"])
    # Combo R$19,00 + muffin discounted to R$7,00 = R$26,00.
    assert order.total_q == 1900 + 700


def test_manual_coupon_does_not_stack_on_promoted_line(client):
    collection, listing = _seed()
    J.seed_product(MUFFIN, "Muffin", 1000, listing=listing, collection=collection, sort_order=4, stock_qty=20)
    J.seed_promotion(name="Semana Doce", kind="percent", value=30, skus=[MUFFIN])  # 30% auto
    J.seed_coupon("MENOS10", kind="percent", value=10, name="Menos 10")  # 10% manual, whole cart
    J.otp_login(client)

    J.set_cart_qty(client, MUFFIN, 1)
    status, body = J.apply_coupon(client, "MENOS10")
    assert status == 200, body
    # Biggest discount wins per line: the 30% promo, not 30%+10%.
    assert body["cart"]["discount_total_q"] == 300
