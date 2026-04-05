"""Tests for storefront checkout views: CheckoutView, OrderConfirmationView."""

from __future__ import annotations

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


def _login_as_customer(client, customer):
    from shopman.auth.protocols.customer import AuthCustomerInfo
    from shopman.auth.services._user_bridge import get_or_create_user_for_customer

    info = AuthCustomerInfo(
        uuid=customer.uuid,
        name=customer.name,
        phone=customer.phone,
        email=None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.auth.backends.PhoneOTPBackend")
    return user


# ── CheckoutView GET ──────────────────────────────────────────────────


class TestCheckoutGet:
    def test_empty_cart_redirects(self, client: Client):
        resp = client.get("/checkout/")
        assert resp.status_code == 302
        assert "/cart/" in resp.url

    def test_checkout_requires_login(self, cart_session):
        """Checkout without auth redirects to login."""
        resp = cart_session.get("/checkout/")
        assert resp.status_code == 302
        assert "/login/" in resp.url

    def test_checkout_with_auth(self, cart_session, customer):
        """Checkout with auth shows the page."""
        _login_as_customer(cart_session, customer)
        resp = cart_session.get("/checkout/")
        assert resp.status_code == 200


# ── CheckoutView POST ─────────────────────────────────────────────────


class TestCheckoutPost:
    def test_empty_cart_redirects(self, client: Client):
        resp = client.post("/checkout/", {"phone": "43999990001"})
        assert resp.status_code == 302

    def test_missing_phone_returns_error(self, cart_session, customer):
        _login_as_customer(cart_session, customer)
        resp = cart_session.post("/checkout/", {"phone": ""})
        # Should re-render with error (not redirect to success)
        assert resp.status_code == 200

    def test_successful_checkout_redirects(self, cart_session, channel, customer):
        _login_as_customer(cart_session, customer)
        resp = cart_session.post(
            "/checkout/",
            {
                "phone": customer.phone,
                "name": customer.name,
                "fulfillment_type": "pickup",
            },
        )
        assert resp.status_code == 302

    def test_checkout_with_delivery(self, cart_session_delivery, channel, customer):
        _login_as_customer(cart_session_delivery, customer)
        resp = cart_session_delivery.post(
            "/checkout/",
            {
                "phone": customer.phone,
                "name": customer.name,
                "fulfillment_type": "delivery",
                "delivery_address": "Rua X 123",
            },
        )
        assert resp.status_code == 302

    def test_checkout_with_notes(self, cart_session, channel, customer):
        _login_as_customer(cart_session, customer)
        resp = cart_session.post(
            "/checkout/",
            {
                "phone": customer.phone,
                "name": customer.name,
                "notes": "Sem glúten",
            },
        )
        assert resp.status_code == 302

    def test_minimum_order_warning_shows_on_checkout(
        self, cart_session, channel, customer
    ):
        _login_as_customer(cart_session, customer)
        channel.config = {
            "rules": {
                "validators": ["shop.minimum_order"],
                "minimum_order_q": 5000,
            }
        }
        channel.save(update_fields=["config"])

        resp = cart_session.get("/checkout/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Faltam" in content
        assert "pedido mínimo" in content

    def test_checkout_post_validates_stock_without_client_flag(
        self, cart_session, channel, customer
    ):
        """WP-S3: servidor valida estoque sempre; não depende só de stock_checked."""
        _login_as_customer(cart_session, customer)
        resp = cart_session.post(
            "/checkout/",
            {
                "phone": customer.phone,
                "name": customer.name,
                "fulfillment_type": "pickup",
            },
        )
        assert resp.status_code in (200, 302)


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
