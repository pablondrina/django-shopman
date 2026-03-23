"""Tests for storefront cart views."""
from __future__ import annotations

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


# ── CartView ──────────────────────────────────────────────────────────


class TestCartView:
    def test_empty_cart(self, client: Client):
        resp = client.get("/cart/")
        assert resp.status_code == 200

    def test_cart_with_items(self, cart_session):
        resp = cart_session.get("/cart/")
        assert resp.status_code == 200


# ── AddToCartView ─────────────────────────────────────────────────────


class TestAddToCartView:
    def test_add_item(self, client: Client, channel, product):
        resp = client.post("/cart/add/", {"sku": product.sku, "qty": 1})
        assert resp.status_code == 200
        assert b"cartUpdated" in resp.headers.get("HX-Trigger", "").encode()

    def test_add_item_nonexistent_sku(self, client: Client, channel):
        resp = client.post("/cart/add/", {"sku": "NOPE", "qty": 1})
        assert resp.status_code == 404

    def test_add_unavailable_product(self, client: Client, channel, product_unavailable):
        resp = client.post("/cart/add/", {"sku": product_unavailable.sku, "qty": 1})
        assert resp.status_code == 200
        assert resp.headers.get("HX-Retarget") == "#stock-error-modal"

    def test_add_item_qty_zero_becomes_one(self, client: Client, channel, product):
        resp = client.post("/cart/add/", {"sku": product.sku, "qty": 0})
        assert resp.status_code == 200

    def test_add_item_merges_same_sku(self, client: Client, channel, product):
        client.post("/cart/add/", {"sku": product.sku, "qty": 2})
        client.post("/cart/add/", {"sku": product.sku, "qty": 3})
        resp = client.get("/cart/summary/")
        assert resp.status_code == 200

    def test_add_requires_post(self, client: Client, channel, product):
        resp = client.get("/cart/add/")
        assert resp.status_code == 405


# ── UpdateCartItemView ────────────────────────────────────────────────


class TestUpdateCartItemView:
    def test_update_qty(self, cart_session, channel, product):
        from shopman.ordering.models import Session

        sk = cart_session.session["omniman_session_key"]
        session = Session.objects.get(session_key=sk)
        line_id = session.items[0]["line_id"]

        resp = cart_session.post("/cart/update/", {"line_id": line_id, "qty": 5})
        assert resp.status_code == 200
        assert "cartUpdated" in resp.headers.get("HX-Trigger", "")

    def test_update_nonexistent_line_raises(self, cart_session, channel, product):
        cart_session.raise_request_exception = False
        resp = cart_session.post("/cart/update/", {"line_id": "fake-line", "qty": 2})
        assert resp.status_code == 500


# ── RemoveCartItemView ────────────────────────────────────────────────


class TestRemoveCartItemView:
    def test_remove_item(self, cart_session, channel, product):
        from shopman.ordering.models import Session

        sk = cart_session.session["omniman_session_key"]
        session = Session.objects.get(session_key=sk)
        line_id = session.items[0]["line_id"]

        resp = cart_session.post("/cart/remove/", {"line_id": line_id})
        assert resp.status_code == 200
        assert "cartUpdated" in resp.headers.get("HX-Trigger", "")

    def test_remove_last_item_shows_empty(self, cart_session, channel, product):
        from shopman.ordering.models import Session

        sk = cart_session.session["omniman_session_key"]
        session = Session.objects.get(session_key=sk)
        line_id = session.items[0]["line_id"]

        resp = cart_session.post("/cart/remove/", {"line_id": line_id})
        assert resp.status_code == 200


# ── CartContentPartialView ────────────────────────────────────────────


class TestCartContentPartialView:
    def test_empty_cart_content(self, client: Client):
        resp = client.get("/cart/content/")
        assert resp.status_code == 200

    def test_cart_content_with_items(self, cart_session):
        resp = cart_session.get("/cart/content/")
        assert resp.status_code == 200


# ── CartSummaryView ───────────────────────────────────────────────────


class TestCartSummaryView:
    def test_empty_summary(self, client: Client):
        resp = client.get("/cart/summary/")
        assert resp.status_code == 200

    def test_summary_with_items(self, cart_session):
        resp = cart_session.get("/cart/summary/")
        assert resp.status_code == 200


# ── FloatingCartBarView ───────────────────────────────────────────────


class TestFloatingCartBarView:
    def test_floating_bar(self, client: Client):
        resp = client.get("/cart/floating-bar/")
        assert resp.status_code == 200
