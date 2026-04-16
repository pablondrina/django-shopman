"""Unit tests for shopman.shop.projections.checkout.

Uses web fixtures from conftest.py. The CheckoutProjection builder
pulls together cart, customer context, payment methods, and shop config
into a frozen dataclass — tests verify stable shape and graceful
degradation when services are unavailable.
"""
from __future__ import annotations

import pytest
from django.test import RequestFactory

from shopman.shop.projections.checkout import CheckoutProjection, build_checkout
from shopman.shop.projections.types import PaymentMethodOptionProjection, PickupSlotProjection
from shopman.shop.web.constants import STOREFRONT_CHANNEL_REF

pytestmark = pytest.mark.django_db


def _request_with_cart_session(client):
    rf = RequestFactory()
    request = rf.get("/checkout/?v2")
    request.session = client.session  # type: ignore[attr-defined]
    return request


def _request_anonymous(client):
    rf = RequestFactory()
    request = rf.get("/checkout/?v2")
    request.session = client.session  # type: ignore[attr-defined]
    request.customer = None
    return request


# ──────────────────────────────────────────────────────────────────────
# Shape
# ──────────────────────────────────────────────────────────────────────


class TestCheckoutProjectionShape:
    def test_returns_checkout_projection(self, cart_session):
        request = _request_with_cart_session(cart_session)
        proj = build_checkout(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        assert isinstance(proj, CheckoutProjection)

    def test_is_immutable(self, cart_session):
        from dataclasses import FrozenInstanceError

        request = _request_with_cart_session(cart_session)
        proj = build_checkout(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        with pytest.raises(FrozenInstanceError):
            proj.customer_phone = "999"  # type: ignore[misc]

    def test_cart_embedded(self, cart_session, product):
        from shopman.shop.projections.cart import CartProjection

        request = _request_with_cart_session(cart_session)
        proj = build_checkout(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        assert isinstance(proj.cart, CartProjection)
        assert not proj.cart.is_empty
        assert len(proj.cart.items) == 1
        assert proj.cart.items[0].sku == product.sku

    def test_empty_cart_is_allowed(self, client):
        rf = RequestFactory()
        request = rf.get("/checkout/?v2")
        request.session = client.session  # type: ignore[attr-defined]
        proj = build_checkout(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        assert isinstance(proj, CheckoutProjection)
        assert proj.cart.is_empty

    def test_unauthenticated_has_empty_addresses(self, cart_session):
        request = _request_with_cart_session(cart_session)
        proj = build_checkout(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        # No customer attached to request — addresses should be empty
        assert proj.saved_addresses == ()
        assert proj.is_authenticated is False
        assert proj.customer_phone == ""
        assert proj.customer_name == ""


# ──────────────────────────────────────────────────────────────────────
# Payment methods
# ──────────────────────────────────────────────────────────────────────


class TestPaymentMethods:
    def test_default_payment_method_from_channel(self, cart_session, channel):
        request = _request_with_cart_session(cart_session)
        proj = build_checkout(request=request, channel_ref=STOREFRONT_CHANNEL_REF)

        assert len(proj.payment_methods) >= 1
        assert all(isinstance(m, PaymentMethodOptionProjection) for m in proj.payment_methods)
        # First method is default
        assert proj.payment_methods[0].is_default is True
        assert proj.default_payment_method == proj.payment_methods[0].ref

    def test_no_channel_falls_back_to_cash(self, cart_session):
        request = _request_with_cart_session(cart_session)
        proj = build_checkout(request=request, channel_ref="nonexistent-channel")
        assert len(proj.payment_methods) == 1
        assert proj.payment_methods[0].ref == "cash"

    def test_pix_method_has_portuguese_label(self, cart_session, channel):
        channel.config = channel.config or {}
        channel.config["payment"] = {"method": ["pix", "cash"]}
        channel.save(update_fields=["config"])

        request = _request_with_cart_session(cart_session)
        proj = build_checkout(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        pix = next((m for m in proj.payment_methods if m.ref == "pix"), None)
        assert pix is not None
        assert pix.label == "PIX"


# ──────────────────────────────────────────────────────────────────────
# Pickup slots
# ──────────────────────────────────────────────────────────────────────


class TestPickupSlots:
    def test_slots_are_pickup_slot_projections(self, cart_session):
        request = _request_with_cart_session(cart_session)
        proj = build_checkout(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        assert all(isinstance(s, PickupSlotProjection) for s in proj.pickup_slots)

    def test_slots_have_ref_label_starts_at(self, cart_session):
        request = _request_with_cart_session(cart_session)
        proj = build_checkout(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        if proj.pickup_slots:
            slot = proj.pickup_slots[0]
            assert slot.ref
            assert slot.label
            assert slot.starts_at


# ──────────────────────────────────────────────────────────────────────
# Shop config
# ──────────────────────────────────────────────────────────────────────


class TestShopConfig:
    def test_default_max_preorder_days(self, cart_session):
        request = _request_with_cart_session(cart_session)
        proj = build_checkout(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        assert proj.max_preorder_days == 30  # default

    def test_closed_dates_json_is_valid(self, cart_session):
        import json

        request = _request_with_cart_session(cart_session)
        proj = build_checkout(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        parsed = json.loads(proj.closed_dates_json)
        assert isinstance(parsed, list)

    def test_custom_max_preorder_days(self, cart_session, shop_instance):
        shop_instance.defaults = {"max_preorder_days": 14}
        shop_instance.save(update_fields=["defaults"])

        request = _request_with_cart_session(cart_session)
        proj = build_checkout(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        assert proj.max_preorder_days == 14
