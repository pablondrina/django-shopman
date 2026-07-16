"""POS D-1 (sobras): the price the operator SEES and SENDS equals what is charged.

After the meta fix (#91) the ``AvailabilityDiscountModifier`` applies the D-1
50% on commit. If the POS kept showing/sending the full catalog price, the
review total (payload-based) would disagree with the committed order (modifier
re-derives the discount) — shown≠charged. The fix exposes ``d1_price_q`` on the
product projection (same rule gate + math as the modifier) so the POS shows and
sends the already-discounted price; review and commit then agree.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.backstage.projections import pos as pos_projection
from shopman.shop.models import Channel, RuleConfig, Shop
from shopman.shop.services import pos as pos_service
from shopman.shop.services import sessions as session_service

pytestmark = pytest.mark.django_db

POS = "pdv"
CATALOG_Q = 90  # R$ 0,90


def _seed_pos_product() -> Product:
    Shop.objects.create(name="Demo", brand_name="Demo", short_name="Demo", phone="554333231997")
    Channel.objects.create(ref=POS, name="PDV")
    listing = Listing.objects.create(ref=POS, name="PDV", is_active=True, priority=10)
    product = Product.objects.create(
        sku="PAO", name="Pão", base_price_q=CATALOG_Q, is_published=True, is_sellable=True,
    )
    ListingItem.objects.create(
        listing=listing, product=product, price_q=CATALOG_Q, is_published=True, is_sellable=True,
    )
    return product


@pytest.fixture
def d1_rule():
    RuleConfig.objects.create(
        ref="d1_discount", rule_path="shopman.shop.rules.pricing.D1Rule",
        label="Desconto D-1 (sobras)", params={"discount_percent": 50},
        enabled=True, priority=15,
    )
    from shopman.shop.rules import engine
    try:
        engine.get_active_rules.cache_clear()  # type: ignore[attr-defined]
    except AttributeError:
        pass


# ── projection price math (mirrors the modifier) ────────────────────────


def test_d1_price_q_applies_rule_percent(d1_rule):
    assert pos_projection._d1_price_q(CATALOG_Q) == 45  # 90 − 50%


def test_d1_price_q_falls_back_to_full_when_rule_off():
    # No RuleConfig → get_channel_rule_params returns None → no discount.
    from shopman.shop.rules import engine
    try:
        engine.get_active_rules.cache_clear()  # type: ignore[attr-defined]
    except AttributeError:
        pass
    assert pos_projection._d1_price_q(CATALOG_Q) == CATALOG_Q


def test_projection_exposes_d1_price_for_d1_line(d1_rule, monkeypatch):
    product = _seed_pos_product()
    from shopman.backstage.projections import _helpers
    monkeypatch.setattr(_helpers, "_line_item_is_d1", lambda *a, **k: True)

    proj = pos_projection._product_projection(product, CATALOG_Q)

    assert proj.is_d1 is True
    assert proj.d1_price_q == 45
    assert proj.d1_price_display == "R$ 0,45"
    assert proj.price_q == CATALOG_Q  # full price still carried for the strike-through


def test_projection_d1_price_equals_full_for_non_d1(d1_rule, monkeypatch):
    product = _seed_pos_product()
    from shopman.backstage.projections import _helpers
    monkeypatch.setattr(_helpers, "_line_item_is_d1", lambda *a, **k: False)

    proj = pos_projection._product_projection(product, CATALOG_Q)

    assert proj.is_d1 is False
    assert proj.d1_price_q == CATALOG_Q  # not active → tile shows single price


# ── the invariant: review total == charged total for a D-1 line ─────────


def test_review_total_matches_committed_charge_for_d1(d1_rule):
    """The POS sends the discounted price; review (payload-based) and the
    modifier-priced session must land on the identical number."""
    _seed_pos_product()
    shown_q = pos_projection._d1_price_q(CATALOG_Q)  # 45 — what the tile shows & sends
    payload = {"items": [{"sku": "PAO", "qty": 1, "unit_price_q": shown_q, "is_d1": True}]}

    # "shown" side — exactly what review_sale returns as total_q.
    review = pos_service.review_sale(channel_ref=POS, payload=payload, operator_username="op")
    assert review.total_q == shown_q

    # "charged" side — build_session_ops → modify_session reprices to catalog then
    # re-applies the D-1 50% via meta.is_d1. This is what close_sale commits.
    ops = pos_service.build_session_ops(payload, "op")
    session = session_service.create_session(POS, data={})
    session = session_service.modify_session(session_key=session.session_key, channel_ref=POS, ops=ops)
    line = next(i for i in session.items if i["sku"] == "PAO")

    assert line["meta"].get("is_d1") is True
    assert line["unit_price_q"] == shown_q  # 45 — charged == shown
    assert int(Decimal(str(line["qty"]))) == 1
