"""Tests for storefront payment view — Stripe Checkout (hosted redirect) wiring."""

from __future__ import annotations

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


@pytest.fixture
def order_card(channel):
    from shopman.orderman.models import Order

    return Order.objects.create(
        ref="ORD-CARD-001",
        channel_ref=channel.ref,
        status="new",
        total_q=1500,
        handle_type="phone",
        handle_ref="5543999990001",
        data={
            "payment": {
                "method": "card",
                "amount_q": 1500,
                "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_demo",
            },
        },
    )


@pytest.fixture
def order_card_pending_url(channel):
    """Card order whose checkout_url is not yet persisted (rare race)."""
    from shopman.orderman.models import Order

    return Order.objects.create(
        ref="ORD-CARD-002",
        channel_ref=channel.ref,
        status="new",
        total_q=1500,
        handle_type="phone",
        handle_ref="5543999990001",
        data={"payment": {"method": "card", "amount_q": 1500}},
    )


class TestPaymentCardPage:
    def test_card_payment_renders_redirect_button(self, client: Client, order_card):
        """Payment page with method=card renders an anchor pointing at checkout.stripe.com."""
        resp = client.get(f"/pedido/{order_card.ref}/pagamento/")
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "Pagar com cartão" in body
        assert "https://checkout.stripe.com/c/pay/cs_test_demo" in body

    def test_card_payment_does_not_load_stripe_js(self, client: Client, order_card):
        """Hosted redirect ⇒ zero stripe.js, zero Elements iframe."""
        resp = client.get(f"/pedido/{order_card.ref}/pagamento/")
        body = resp.content.decode()
        assert "js.stripe.com" not in body
        assert "stripe-payment-element" not in body
        assert "Stripe(" not in body

    def test_card_payment_omotenashi_intro_present(self, client: Client, order_card):
        resp = client.get(f"/pedido/{order_card.ref}/pagamento/")
        body = resp.content.decode()
        assert "ambiente seguro do Stripe" in body
        assert "não recebemos os dados do seu cartão" in body

    def test_card_payment_without_url_shows_pending_copy(
        self, client: Client, order_card_pending_url,
    ):
        """If checkout_url is missing, render a graceful pending message (no broken link)."""
        resp = client.get(f"/pedido/{order_card_pending_url.ref}/pagamento/")
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "Preparando ambiente seguro" in body
        # Should NOT render a button with empty href
        assert 'href=""' not in body
