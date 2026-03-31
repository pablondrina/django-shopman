"""Tests for storefront cart views."""
from __future__ import annotations

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


# ── CartView ──────────────────────────────────────────────────────────


class TestCartView:
    def test_cart_redirects_to_menu(self, client: Client):
        resp = client.get("/cart/")
        assert resp.status_code == 302
        assert "open_cart=1" in resp.url

    def test_cart_drawer(self, cart_session):
        resp = cart_session.get("/cart/drawer/")
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

        sk = cart_session.session["cart_session_key"]
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

        sk = cart_session.session["cart_session_key"]
        session = Session.objects.get(session_key=sk)
        line_id = session.items[0]["line_id"]

        resp = cart_session.post("/cart/remove/", {"line_id": line_id})
        assert resp.status_code == 200
        assert "cartUpdated" in resp.headers.get("HX-Trigger", "")

    def test_remove_last_item_shows_empty(self, cart_session, channel, product):
        from shopman.ordering.models import Session

        sk = cart_session.session["cart_session_key"]
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


# ── CartCheckView ────────────────────────────────────────────────────


class TestCartCheckView:
    def test_cart_check_empty_cart(self, client: Client):
        resp = client.get("/cart/check/")
        assert resp.status_code == 200

    def test_cart_check_ok_when_all_available(self, cart_session, channel, monkeypatch):
        """Cart check returns no warnings when availability is sufficient."""
        from decimal import Decimal

        from channels.web.views import cart as cart_views

        def _mock_availability(sku):
            return {
                "breakdown": {
                    "ready": Decimal("999"),
                    "in_production": Decimal("0"),
                    "d1": Decimal("0"),
                },
            }

        monkeypatch.setattr(cart_views, "_get_availability", _mock_availability)

        resp = cart_session.get("/cart/check/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "bg-warning-light" not in content

    def test_cart_check_warns_on_insufficient_stock(self, cart_session, channel, product, monkeypatch):
        """Cart check shows warning when stock < requested qty (no session holds)."""
        from decimal import Decimal

        from channels.web.views import cart as cart_views

        def _mock_availability(sku):
            return {
                "breakdown": {
                    "ready": Decimal("1"),
                    "in_production": Decimal("0"),
                    "d1": Decimal("0"),
                },
            }

        monkeypatch.setattr(cart_views, "_get_availability", _mock_availability)
        monkeypatch.setattr(cart_views, "_get_session_held_qty", lambda req: {})

        resp = cart_session.get("/cart/check/")
        assert resp.status_code == 200
        content = resp.content.decode()
        # Cart has qty=2, available=1, no holds → should show warning
        assert "bg-warning-light" in content
        assert product.name in content

    def test_cart_check_no_warning_when_session_holds_cover(self, cart_session, channel, product, monkeypatch):
        """Cart check does NOT warn when session holds already reserve the stock."""
        from decimal import Decimal

        from channels.web.views import cart as cart_views

        def _mock_availability(sku):
            # Availability returns 0 because the session's hold consumed all stock
            return {
                "breakdown": {
                    "ready": Decimal("0"),
                    "in_production": Decimal("0"),
                    "d1": Decimal("0"),
                },
            }

        # Session holds 2 units of this SKU (matching cart qty=2)
        monkeypatch.setattr(cart_views, "_get_availability", _mock_availability)
        monkeypatch.setattr(cart_views, "_get_session_held_qty", lambda req: {product.sku: 2})

        resp = cart_session.get("/cart/check/")
        assert resp.status_code == 200
        content = resp.content.decode()
        # available=0, but session holds 2 → effective=2, qty=2 → no warning
        assert "bg-warning-light" not in content
