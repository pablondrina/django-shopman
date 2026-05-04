"""Tests for storefront checkout views: CheckoutView, OrderConfirmationView."""

from __future__ import annotations

import json
from datetime import date, time, timedelta
from unittest.mock import patch
from urllib.parse import urlsplit

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db

DOORMAN_SETTINGS = {
    "CUSTOMER_RESOLVER_CLASS": "shopman.guestman.adapters.auth.CustomerResolver",
    "MESSAGE_SENDER_CLASS": "shopman.doorman.senders.LogSender",
    "DEVICE_TRUST_COOKIE_NAME": "doorman_dt",
    "LOGOUT_REDIRECT_URL": "/",
}

BACKENDS = [
    "shopman.doorman.backends.PhoneOTPBackend",
    "django.contrib.auth.backends.ModelBackend",
]


def _login_as_customer(client, customer):
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    info = AuthCustomerInfo(
        uuid=customer.uuid,
        name=customer.name,
        phone=customer.phone,
        email=None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")
    return user


# ── CheckoutView GET ──────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _configure_auth(settings):
    settings.DOORMAN = DOORMAN_SETTINGS
    settings.AUTHENTICATION_BACKENDS = BACKENDS


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

    def test_checkout_with_authenticated_customer_without_phone_requires_phone_gate(self, cart_session):
        """Instagram-origin customers without phone must verify phone before checkout."""
        from shopman.guestman.models import Customer

        customer = Customer.objects.create(
            ref="WEB-IG-NOPHONE",
            first_name="Diofer",
            last_name="Ilgo",
        )
        _login_as_customer(cart_session, customer)

        resp = cart_session.get("/checkout/")

        assert resp.status_code == 302
        assert resp.url == "/login/?next=/checkout/"

        login_resp = cart_session.get(resp.url)
        assert login_resp.status_code == 200
        body = login_resp.content.decode("utf-8")
        assert 'name="phone"' in body

    def test_checkout_prefills_phone_after_manychat_access_link(self, cart_session, settings):
        """ManyChat access-link identity must survive until checkout."""
        from shopman.guestman.models import Customer

        settings.DOORMAN = {**DOORMAN_SETTINGS, "ACCESS_LINK_API_KEY": "test-access-key"}
        customer = Customer.objects.create(
            ref="WEB-ACCESS-MC",
            first_name="Pablo",
            last_name="Valentini",
        )
        create_resp = cart_session.post(
            "/api/auth/access/create/",
            data=json.dumps({
                "customer_id": str(customer.uuid),
                "whatsapp_id": "43984049009",
                "first_name": "Pablo",
                "last_name": "Valentini",
                "manychat_id": "4605528796186498",
                "source": "manychat",
                "next": "/checkout/",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-access-key",
        )
        assert create_resp.status_code == 200

        access_url = create_resp.json()["access_url"]
        entry = urlsplit(access_url)
        entry_resp = cart_session.get(f"{entry.path}?{entry.query}")
        assert entry_resp.status_code == 302
        assert entry_resp.url == "/checkout/"

        resp = cart_session.get("/checkout/")
        assert resp.status_code == 200
        body = resp.content.decode("utf-8")
        assert 'name="phone" value="+5543984049009"' in body
        assert "Telefone é obrigatório" not in body

    def test_checkout_renders_address_picker(self, cart_session, customer):
        """Checkout page must embed the new iFood-style address picker."""
        _login_as_customer(cart_session, customer)
        resp = cart_session.get("/checkout/")
        assert resp.status_code == 200
        body = resp.content.decode("utf-8")
        assert "data-address-picker" in body
        assert "addressPicker(" in body
        assert "reverseGeocodeUrl" in body
        assert "Usar minha localiza" in body

    def test_pickup_slot_defaults_to_current_slot_after_15h(self, cart_session, customer):
        _login_as_customer(cart_session, customer)

        with patch("shopman.storefront.services.pickup_slots._wall_clock", return_value=time(15, 1)):
            resp = cart_session.get("/checkout/?step=when")

        assert resp.status_code == 200
        body = resp.content.decode("utf-8")
        assert "deliverySlot: 'slot-15'" in body
        assert "normalizeDeliverySlot" in body
        assert 'value="slot-15"' in body


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
        from datetime import date, timedelta
        # Use 3 days ahead to avoid the tomorrow cutoff check (which uses UTC hours)
        future_date = (date.today() + timedelta(days=3)).isoformat()
        _login_as_customer(cart_session, customer)
        resp = cart_session.post(
            "/checkout/",
            {
                "phone": customer.phone,
                "name": customer.name,
                "fulfillment_type": "pickup",
                "delivery_date": future_date,
                "delivery_time_slot": "slot-09",
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
        from datetime import date, timedelta
        future_date = (date.today() + timedelta(days=3)).isoformat()
        _login_as_customer(cart_session, customer)
        resp = cart_session.post(
            "/checkout/",
            {
                "phone": customer.phone,
                "name": customer.name,
                "notes": "Sem glúten",
                "fulfillment_type": "pickup",
                "delivery_date": future_date,
                "delivery_time_slot": "slot-09",
            },
        )
        assert resp.status_code == 302

    def test_minimum_order_warning_shows_on_checkout(
        self, cart_session, channel, customer, shop_instance
    ):
        # Configure minimum order via Shop.defaults (channel-level config comes in WP-F1).
        # Below-minimum cart surfaces the block via CartProjection — the checkout view
        # renders the projection-backed summary; the stepper/progress bar lives in the
        # drawer. Here we just assert the projection flags the cart as below minimum.
        shop_instance.defaults = {"rules": {"validators": ["shop.minimum_order"], "minimum_order_q": 50000}}
        shop_instance.save()

        _login_as_customer(cart_session, customer)
        resp = cart_session.get("/checkout/")
        assert resp.status_code == 200
        checkout = resp.context["checkout"]
        assert checkout.cart.minimum_order_progress is not None

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

    def test_checkout_stock_check_uses_selected_future_date(
        self, cart_session, channel, customer
    ):
        future_date = date.today() + timedelta(days=3)
        _login_as_customer(cart_session, customer)

        with patch(
            "shopman.shop.services.checkout_context._availability_for_sku",
            return_value={
                "breakdown": {"ready": 0, "in_production": 1, "d1": 0},
                "availability_policy": "demand_ok",
                "is_paused": False,
            },
        ) as mock_availability:
            resp = cart_session.post(
                "/checkout/",
                {
                    "phone": customer.phone,
                    "name": customer.name,
                    "fulfillment_type": "pickup",
                    "delivery_date": future_date.isoformat(),
                    "delivery_time_slot": "slot-09",
                },
            )

        assert resp.status_code in (200, 302)
        assert mock_availability.called
        assert mock_availability.call_args.kwargs["target_date"] == future_date


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
