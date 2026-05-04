"""Tests for storefront payment view — Stripe Checkout (hosted redirect) wiring."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings
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


@pytest.fixture
def order_pix_without_intent(channel):
    from shopman.orderman.models import Order

    return Order.objects.create(
        ref="ORD-PIX-NO-INTENT",
        channel_ref=channel.ref,
        status="new",
        total_q=1500,
        handle_type="phone",
        handle_ref="5543999990001",
        data={"payment": {"method": "pix", "amount_q": 1500}},
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
        assert "Pagamento seguro com cartão" in body
        assert "A disponibilidade foi confirmada" in body
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


class TestPaymentIntentRecovery:
    @override_settings(DEBUG=True)
    def test_unconfirmed_pix_payment_page_redirects_to_tracking_without_intent(
        self,
        client: Client,
        order_pix_without_intent,
    ):
        from shopman.payman.models import PaymentIntent

        resp = client.get(f"/pedido/{order_pix_without_intent.ref}/pagamento/")

        assert resp.status_code == 302
        assert resp["Location"] == f"/pedido/{order_pix_without_intent.ref}/"
        order_pix_without_intent.refresh_from_db()
        intent_ref = order_pix_without_intent.data["payment"].get("intent_ref")
        assert intent_ref is None
        assert not PaymentIntent.objects.filter(order_ref=order_pix_without_intent.ref).exists()

    @override_settings(DEBUG=True)
    def test_mock_confirm_does_not_create_pix_before_store_confirmation(
        self,
        client: Client,
        order_pix_without_intent,
    ):
        from shopman.payman.models import PaymentIntent

        resp = client.post(
            f"/pedido/{order_pix_without_intent.ref}/pagamento/mock-confirm/",
            follow=True,
        )

        assert resp.status_code == 200
        order_pix_without_intent.refresh_from_db()
        intent_ref = order_pix_without_intent.data["payment"].get("intent_ref")
        assert intent_ref is None
        assert not PaymentIntent.objects.filter(order_ref=order_pix_without_intent.ref).exists()
        body = resp.content.decode()
        assert "Aguardando confirmação" in body
        assert "Aguardando pagamento" not in body

    def test_expired_confirmed_pix_payment_page_cancels_and_redirects_to_tracking(
        self,
        client: Client,
        order_pix_without_intent,
    ):
        from django.utils import timezone

        order_pix_without_intent.status = "confirmed"
        order_pix_without_intent.data["payment"]["expires_at"] = (
            timezone.now().replace(microsecond=0) - timezone.timedelta(minutes=1)
        ).isoformat()
        order_pix_without_intent.save(update_fields=["status", "data", "updated_at"])

        resp = client.get(f"/pedido/{order_pix_without_intent.ref}/pagamento/")

        assert resp.status_code == 302
        assert resp["Location"] == f"/pedido/{order_pix_without_intent.ref}/"
        order_pix_without_intent.refresh_from_db()
        assert order_pix_without_intent.status == "cancelled"
        assert order_pix_without_intent.data["cancellation_reason"] == "payment_timeout"
        assert "payment_timeout_at" in order_pix_without_intent.data

    @override_settings(DEBUG=True)
    def test_confirmed_pix_payment_page_recovers_stale_generation_error(
        self,
        client: Client,
        order_pix_without_intent,
    ):
        from shopman.payman.models import PaymentIntent

        order_pix_without_intent.status = "confirmed"
        order_pix_without_intent.data["payment"]["error"] = "No module named 'qrcode'"
        order_pix_without_intent.save(update_fields=["status", "data", "updated_at"])

        resp = client.get(f"/pedido/{order_pix_without_intent.ref}/pagamento/")

        assert resp.status_code == 200
        order_pix_without_intent.refresh_from_db()
        payment = order_pix_without_intent.data["payment"]
        assert "error" not in payment
        assert payment["intent_ref"]
        assert payment["qr_code"].startswith("data:image/png;base64,")
        assert payment["copy_paste"].startswith("000201")
        assert PaymentIntent.objects.filter(order_ref=order_pix_without_intent.ref).exists()
        body = resp.content.decode()
        assert "Pagamento Pix" in body
        assert "A disponibilidade foi confirmada" in body
        assert "Se o prazo expirar" in body
        assert "QR Code PIX" in body
        assert "Não conseguimos gerar o pagamento agora." not in body

    def test_confirmed_pix_payment_page_shows_recoverable_error_when_gateway_fails(
        self,
        client: Client,
        order_pix_without_intent,
    ):
        order_pix_without_intent.status = "confirmed"
        order_pix_without_intent.save(update_fields=["status", "updated_at"])

        mock_adapter = MagicMock()
        mock_adapter.create_intent.side_effect = TimeoutError("Gateway timeout")

        with patch("shopman.shop.services.payment.get_adapter", return_value=mock_adapter):
            resp = client.get(f"/pedido/{order_pix_without_intent.ref}/pagamento/")

        assert resp.status_code == 200
        order_pix_without_intent.refresh_from_db()
        assert "Gateway timeout" in order_pix_without_intent.data["payment"]["error"]
        body = resp.content.decode()
        assert "Não conseguimos preparar o pagamento" in body
        assert "Se o erro continuar" in body
        assert "Não conseguimos gerar o pagamento agora." in body
        assert "Tentar novamente" in body
        assert f"/pedido/{order_pix_without_intent.ref}/pagamento/" in body
        assert "QR Code PIX" not in body
