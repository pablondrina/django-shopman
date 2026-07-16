"""E2E: the D-1 (sobras) clearance discount through the real storefront cart.

Drives ``CartService.add_item`` — the same path the add-to-cart intent uses —
against a real product, real reservable stock and a real ``d1_discount``
RuleConfig. No durable state (``session.data["availability"]``) is injected: the
only signal is ``is_d1=True`` on the add call, exactly as the vitrine passes it
from ``cart_context._is_d1``. Guards the regression where a top-level ``is_d1``
was stripped by ``Session._normalize_items`` and the 50% never applied.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.shop.models import Channel, RuleConfig, Shop
from shopman.storefront.cart import CartService

pytestmark = pytest.mark.django_db

BASE_Q = 90  # R$ 0,90


def _make_request():
    from django.test import RequestFactory

    req = RequestFactory().get("/")
    req.session = {}
    return req


def _seed_product_with_stock(qty: Decimal = Decimal("10")) -> Product:
    Shop.objects.create(name="Demo", brand_name="Demo", short_name="Demo", phone="554333231997")
    Channel.objects.create(ref="web", name="Loja Online")
    listing = Listing.objects.create(ref="web", name="Web", is_active=True, priority=10)
    product = Product.objects.create(
        sku="PAO-FRANCES", name="Pão Francês", base_price_q=BASE_Q,
        is_published=True, is_sellable=True,
    )
    ListingItem.objects.create(
        listing=listing, product=product, price_q=BASE_Q, is_published=True, is_sellable=True,
    )
    from shopman.stockman import stock
    from shopman.stockman.models import Position, PositionKind

    position, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    stock.receive(quantity=qty, sku=product.sku, position=position,
                  target_date=date.today(), reason="d1 e2e seed")
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


def _cart_line(session):
    return session.items[0]


def test_add_to_cart_d1_applies_clearance_discount(d1_rule):
    _seed_product_with_stock()
    req = _make_request()

    session = CartService.add_item(
        req, sku="PAO-FRANCES", qty=1, unit_price_q=BASE_Q, name="Pão Francês", is_d1=True,
    )

    line = _cart_line(session)
    assert line["meta"].get("is_d1") is True
    assert line["unit_price_q"] == 45  # 90 − 50%
    assert session.pricing.get("d1_discount", {}).get("total_discount_q") == 45


def test_add_to_cart_without_d1_charges_full_price(d1_rule):
    _seed_product_with_stock()
    req = _make_request()

    session = CartService.add_item(
        req, sku="PAO-FRANCES", qty=1, unit_price_q=BASE_Q, name="Pão Francês", is_d1=False,
    )

    line = _cart_line(session)
    assert not (line.get("meta") or {}).get("is_d1")
    assert line["unit_price_q"] == BASE_Q
    assert "d1_discount" not in (session.pricing or {})


def test_d1_discount_is_idempotent_on_requantity(d1_rule):
    """Bumping qty re-runs the whole pipeline; the 50% must not compound
    (pricing.item restores the catalog base each pass before re-applying)."""
    _seed_product_with_stock()
    req = _make_request()

    CartService.add_item(req, sku="PAO-FRANCES", qty=1, unit_price_q=BASE_Q, is_d1=True)
    # Second add merges into the same line (set_qty → full re-price pass).
    session = CartService.add_item(req, sku="PAO-FRANCES", qty=1, unit_price_q=BASE_Q, is_d1=True)

    line = _cart_line(session)
    assert int(Decimal(str(line["qty"]))) == 2
    assert line["unit_price_q"] == 45  # still 50% off base, never 22
    assert line["line_total_q"] == 90  # 2 × 45
