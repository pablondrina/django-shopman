"""Unit tests for shopman.shop.projections.cart.

Uses the `cart_session` fixture (from conftest.py) which seeds a cart with
the default product, so the projection builder has a real Orderman session
+ ListingItem + stock to work against.
"""
from __future__ import annotations

import pytest
from django.test import RequestFactory
from shopman.orderman.models import Session

from shopman.storefront.projections import build_cart
from shopman.storefront.projections.cart import (
    CartItemProjection,
    CartProjection,
    MinimumOrderProgressProjection,
)
from shopman.storefront.constants import STOREFRONT_CHANNEL_REF

pytestmark = pytest.mark.django_db


def _request_with_cart_session(client):
    """Build a RequestFactory request wearing the session key of ``client``.

    ``cart_session`` in conftest returns a Django test client that has
    already POSTed to /cart/add/. We need a plain ``HttpRequest`` whose
    ``request.session`` holds the same ``cart_session_key``; the projection
    builder reads it via ``CartService.get_cart(request)``.
    """
    rf = RequestFactory()
    request = rf.get("/carrinho/")
    request.session = client.session  # type: ignore[attr-defined]
    return request


# ──────────────────────────────────────────────────────────────────────
# Empty cart
# ──────────────────────────────────────────────────────────────────────


class TestEmptyCart:
    def test_empty_cart_has_stable_shape(self, client):
        rf = RequestFactory()
        request = rf.get("/carrinho/")
        request.session = client.session  # type: ignore[attr-defined]

        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)

        assert isinstance(proj, CartProjection)
        assert proj.is_empty is True
        assert proj.items == ()
        assert proj.items_count == 0
        assert proj.subtotal_q == 0
        assert proj.subtotal_display == "R$ 0,00"
        assert proj.grand_total_q == 0
        assert proj.has_discount is False
        assert proj.has_unavailable_items is False
        assert proj.coupon_code is None
        assert proj.minimum_order_progress is None
        assert proj.upsell is None


# ──────────────────────────────────────────────────────────────────────
# Populated cart
# ──────────────────────────────────────────────────────────────────────


class TestPopulatedCart:
    def test_basic_shape(self, cart_session, product):
        # cart_session added 2x product at the resolved unit price.
        request = _request_with_cart_session(cart_session)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)

        assert proj.is_empty is False
        assert len(proj.items) == 1
        item = proj.items[0]
        assert isinstance(item, CartItemProjection)
        assert item.sku == product.sku
        assert item.name == "Pão Francês"
        assert item.qty == 2
        assert item.unit_price_q > 0
        assert item.total_price_q == item.unit_price_q * 2
        assert item.price_display.startswith("R$ ")
        assert item.total_display.startswith("R$ ")
        assert item.is_available is True
        assert item.availability_warning is None

        assert proj.items_count == 2
        assert proj.subtotal_q == item.total_price_q
        assert proj.grand_total_q == item.total_price_q

    def test_projection_is_immutable(self, cart_session):
        from dataclasses import FrozenInstanceError

        request = _request_with_cart_session(cart_session)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        with pytest.raises(FrozenInstanceError):
            proj.items_count = 99  # type: ignore[misc]

    def test_item_is_immutable(self, cart_session):
        from dataclasses import FrozenInstanceError

        request = _request_with_cart_session(cart_session)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        with pytest.raises(FrozenInstanceError):
            proj.items[0].qty = 99  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────────────
# Availability — own-hold correction
# ──────────────────────────────────────────────────────────────────────


class TestAvailabilityOwnHoldCorrection:
    """Regression: a cart line is only flagged unavailable when the shortage
    is real (external), not when the customer's own hold is the reason
    ``total_promisable`` hit zero.

    Previously the cart compared ``total_promisable < line.qty`` without
    knowing that ``total_promisable`` excludes the session's own hold.
    A customer who bought the entire physical stock saw "Acabou no momento"
    next to their own N units — nonsensical.
    """

    def test_cart_holding_all_physical_stock_shows_no_warning(
        self, client, channel, product,
    ):
        """Stock=5, cart=5 (all reserved by own hold) → no warning."""
        from datetime import date
        from decimal import Decimal

        from shopman.stockman import stock
        from shopman.stockman.models import Position, PositionKind

        from shopman.storefront.tests.web.conftest import _ensure_listing_item

        _ensure_listing_item(channel, product, price_q=90)
        position, _ = Position.objects.get_or_create(
            ref="loja",
            defaults={
                "name": "Loja Principal",
                "kind": PositionKind.PHYSICAL,
                "is_saleable": True,
            },
        )
        stock.receive(
            quantity=Decimal("5"),
            sku=product.sku,
            position=position,
            target_date=date.today(),
            reason="own-hold regression seed",
        )

        resp = client.post("/cart/add/", {"sku": product.sku, "qty": 5})
        assert resp.status_code in (200, 201), (
            "adding all available stock must succeed — hold protects the qty"
        )

        request = _request_with_cart_session(client)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)

        assert len(proj.items) == 1
        item = proj.items[0]
        assert item.qty == 5
        assert item.is_available is True, (
            "session holding all its own stock must NOT be flagged unavailable"
        )
        assert item.availability_warning is None


# ──────────────────────────────────────────────────────────────────────
# Minimum order progress
# ──────────────────────────────────────────────────────────────────────


class TestMinimumOrderProgress:
    def test_progress_shown_when_rule_active(
        self, cart_session, channel, settings,
    ):
        # Activate the shop.minimum_order validator on the channel config.
        channel.config = channel.config or {}
        channel.config.setdefault("rules", {})["validators"] = ["shop.minimum_order"]
        channel.save(update_fields=["config"])

        # Bump the shop default to R$ 50,00 (5000q); the cart is R$ 1,80 → way below.
        from shopman.shop.models import Shop

        shop = Shop.load()
        shop.defaults = shop.defaults or {}
        shop.defaults.setdefault("rules", {})["minimum_order_q"] = 5000
        shop.save(update_fields=["defaults"])

        request = _request_with_cart_session(cart_session)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)

        assert proj.minimum_order_progress is not None
        progress = proj.minimum_order_progress
        assert isinstance(progress, MinimumOrderProgressProjection)
        assert progress.minimum_q == 5000
        assert progress.remaining_q == 5000 - proj.subtotal_q
        assert progress.minimum_display == "R$ 50,00"
        assert 0 <= progress.percent <= 100

    def test_no_progress_when_rule_inactive(self, cart_session):
        # Explicitly disable validators on the channel ([] = run none).
        from shopman.shop.models import Channel
        channel = Channel.objects.get(ref=STOREFRONT_CHANNEL_REF)
        channel.config = channel.config or {}
        channel.config.setdefault("rules", {})["validators"] = []
        channel.save(update_fields=["config"])

        request = _request_with_cart_session(cart_session)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        assert proj.minimum_order_progress is None


# ──────────────────────────────────────────────────────────────────────
# Discount lines
# ──────────────────────────────────────────────────────────────────────


class TestDiscounts:
    def test_discount_line_reflected(self, cart_session):
        # Inject a fake discount breakdown into the Orderman session so the
        # builder has a pricing snapshot to translate. This mirrors what
        # DiscountModifier would write during modify_session().
        session = Session.objects.get(channel_ref=STOREFRONT_CHANNEL_REF, state="open")
        session.pricing = {
            "discount": {
                "total_discount_q": 40,
                "items": [
                    {
                        "sku": "PAO-FRANCES",
                        "name": "Promoção Teste",
                        "type": "promotion",
                        "qty": 2,
                        "discount_q": 20,
                        "original_price_q": 100,
                    },
                ],
            },
        }
        session.save(update_fields=["pricing"])

        request = _request_with_cart_session(cart_session)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)

        assert proj.has_discount is True
        assert proj.discount_total_q == 40
        assert proj.discount_total_display == "R$ 0,40"
        assert len(proj.discount_lines) == 1
        row = proj.discount_lines[0]
        assert row.label == "Promoção Teste"
        assert row.amount_q == 40
        assert row.amount_display == "R$ 0,40"
