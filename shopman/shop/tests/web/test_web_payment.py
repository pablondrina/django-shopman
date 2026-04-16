"""Tests for storefront payment view — Stripe card wiring."""

from __future__ import annotations

import pytest
from django.test import Client, override_settings

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
                "status": "pending",
                "amount_q": 1500,
                "client_secret": "pi_test_secret_xxx",
            },
        },
    )


class TestPaymentCardPage:
    @override_settings(STRIPE_PUBLISHABLE_KEY="pk_test_abc123")
    def test_card_payment_renders_stripe_element(self, client: Client, order_card):
        """Payment page with method=card renders #stripe-payment-element."""
        resp = client.get(f"/pedido/{order_card.ref}/pagamento/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "stripe-payment-element" in content

    @override_settings(STRIPE_PUBLISHABLE_KEY="pk_test_abc123")
    def test_card_payment_renders_meta_tag(self, client: Client, order_card):
        """Payment page with a configured STRIPE_PUBLISHABLE_KEY renders the meta tag."""
        resp = client.get(f"/pedido/{order_card.ref}/pagamento/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert '<meta name="stripe-key"' in content
        assert "pk_test_abc123" in content

    @override_settings(STRIPE_PUBLISHABLE_KEY="")
    def test_no_meta_tag_when_key_not_configured(self, client: Client, order_card):
        """When STRIPE_PUBLISHABLE_KEY is empty, the meta tag is not rendered."""
        resp = client.get(f"/pedido/{order_card.ref}/pagamento/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert '<meta name="stripe-key"' not in content
