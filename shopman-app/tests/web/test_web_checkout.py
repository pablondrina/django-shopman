"""Tests for storefront checkout views: CheckoutView, OrderConfirmationView."""
from __future__ import annotations

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


# ── CheckoutView GET ──────────────────────────────────────────────────


class TestCheckoutGet:
    def test_empty_cart_redirects(self, client: Client):
        resp = client.get("/checkout/")
        assert resp.status_code == 302
        assert "/cart/" in resp.url

    def test_checkout_with_items(self, cart_session):
        resp = cart_session.get("/checkout/")
        assert resp.status_code == 200

    def test_checkout_prefills_verified_phone(self, cart_session):
        session = cart_session.session
        session["storefront_verified_phone"] = "5543999990001"
        session["storefront_verified_name"] = "João"
        session.save()

        resp = cart_session.get("/checkout/")
        assert resp.status_code == 200
        assert b"5543999990001" in resp.content or b"Jo\xc3\xa3o" in resp.content


# ── CheckoutView POST ─────────────────────────────────────────────────


class TestCheckoutPost:
    def test_empty_cart_redirects(self, client: Client):
        resp = client.post("/checkout/", {"name": "X", "phone": "43999990001"})
        assert resp.status_code == 302

    def test_missing_name(self, cart_session):
        resp = cart_session.post("/checkout/", {"phone": "43999990001"})
        assert resp.status_code == 200
        assert "obrigat" in resp.content.decode().lower()

    def test_missing_phone(self, cart_session):
        resp = cart_session.post("/checkout/", {"name": "Test"})
        assert resp.status_code == 200
        assert "obrigat" in resp.content.decode().lower()

    def test_invalid_phone(self, cart_session):
        resp = cart_session.post("/checkout/", {"name": "Test", "phone": "123"})
        assert resp.status_code == 200
        assert "inv" in resp.content.decode().lower()

    def test_successful_checkout_redirects(self, cart_session, channel):
        resp = cart_session.post("/checkout/", {
            "name": "João Silva",
            "phone": "43999990001",
            "fulfillment_type": "pickup",
        })
        # Should redirect to tracking or payment
        assert resp.status_code == 302

    def test_checkout_with_delivery(self, cart_session, channel):
        resp = cart_session.post("/checkout/", {
            "name": "João",
            "phone": "43999990001",
            "fulfillment_type": "delivery",
            "delivery_address": "Rua X 123",
        })
        assert resp.status_code == 302

    def test_checkout_with_notes(self, cart_session, channel):
        resp = cart_session.post("/checkout/", {
            "name": "João",
            "phone": "43999990001",
            "notes": "Sem glúten",
        })
        assert resp.status_code == 302


# ── OrderConfirmationView ─────────────────────────────────────────────


class TestOrderConfirmationView:
    def test_order_confirmation(self, client: Client, order_items):
        resp = client.get(f"/pedido/{order_items.ref}/confirmacao/")
        assert resp.status_code == 200
        assert b"ORD-001" in resp.content

    def test_order_confirmation_not_found(self, client: Client):
        resp = client.get("/pedido/FAKE-REF/confirmacao/")
        assert resp.status_code == 404

    def test_order_confirmation_shows_items(self, client: Client, order_items):
        resp = client.get(f"/pedido/{order_items.ref}/confirmacao/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Francês" in content or "PAO-FRANCES" in content

    def test_order_confirmation_shows_total(self, client: Client, order_items):
        resp = client.get(f"/pedido/{order_items.ref}/confirmacao/")
        assert resp.status_code == 200
        assert b"16,00" in resp.content
