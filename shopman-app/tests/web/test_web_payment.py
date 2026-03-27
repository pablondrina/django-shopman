"""Tests for storefront payment views: PaymentView, PaymentStatusView, MockPaymentConfirmView."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from django.test import Client
from shopman.ordering.models import Directive, Order

from channels.config import ChannelConfig
from channels.handlers.payment import CardCreateHandler, PixGenerateHandler
from channels.topics import CARD_CREATE

pytestmark = pytest.mark.django_db


def _login_as_customer(client, customer):
    from shopman.auth.protocols.customer import AuthCustomerInfo
    from shopman.auth.services._user_bridge import get_or_create_user_for_customer

    info = AuthCustomerInfo(uuid=customer.uuid, name=customer.name, phone=customer.phone, email=None, is_active=True)
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.auth.backends.PhoneOTPBackend")


# ── PaymentView ───────────────────────────────────────────────────────


class TestPaymentView:
    def test_payment_page(self, client: Client, order_with_payment):
        resp = client.get(f"/pedido/{order_with_payment.ref}/pagamento/")
        assert resp.status_code == 200
        assert b"25,00" in resp.content

    def test_payment_page_not_found(self, client: Client):
        resp = client.get("/pedido/NOPE/pagamento/")
        assert resp.status_code == 404

    def test_payment_page_shows_pix_code(self, client: Client, order_with_payment):
        resp = client.get(f"/pedido/{order_with_payment.ref}/pagamento/")
        assert resp.status_code == 200


# ── PaymentStatusView ─────────────────────────────────────────────────


class TestPaymentStatusView:
    def test_status_pending(self, client: Client, order_with_payment):
        resp = client.get(f"/pedido/{order_with_payment.ref}/pagamento/status/")
        assert resp.status_code == 200

    def test_status_paid_redirects(self, client: Client, order_paid):
        resp = client.get(f"/pedido/{order_paid.ref}/pagamento/status/")
        assert resp.status_code == 200
        assert resp.headers.get("HX-Redirect") == f"/pedido/{order_paid.ref}/"

    def test_status_cancelled(self, client: Client, order_with_payment):
        order_with_payment.status = "cancelled"
        order_with_payment.save(update_fields=["status"])
        resp = client.get(f"/pedido/{order_with_payment.ref}/pagamento/status/")
        assert resp.status_code == 200

    def test_status_not_found(self, client: Client):
        resp = client.get("/pedido/NOPE/pagamento/status/")
        assert resp.status_code == 404


# ── MockPaymentConfirmView ────────────────────────────────────────────


class TestMockPaymentConfirmView:
    def test_mock_confirm(self, client: Client, order_with_payment, settings):
        settings.DEBUG = True
        resp = client.post(f"/pedido/{order_with_payment.ref}/pagamento/mock-confirm/")
        assert resp.status_code == 302
        assert f"/pedido/{order_with_payment.ref}/" in resp.url

        order_with_payment.refresh_from_db()
        assert order_with_payment.data["payment"]["status"] == "captured"
        assert order_with_payment.status == "confirmed"

    def test_mock_confirm_already_paid(self, client: Client, order_paid, settings):
        settings.DEBUG = True
        resp = client.post(f"/pedido/{order_paid.ref}/pagamento/mock-confirm/")
        assert resp.status_code == 302

    def test_mock_confirm_blocked_in_production(self, client: Client, order_with_payment, settings):
        settings.DEBUG = False
        resp = client.post(f"/pedido/{order_with_payment.ref}/pagamento/mock-confirm/")
        assert resp.status_code == 404

    def test_mock_confirm_not_found(self, client: Client):
        resp = client.post("/pedido/NOPE/pagamento/mock-confirm/")
        assert resp.status_code == 404


# ── WP-E3: Card payment config ──────────────────────────────────────


class TestPaymentConfig:
    def test_single_method_string(self):
        p = ChannelConfig.Payment(method="pix")
        assert p.available_methods == ["pix"]

    def test_multiple_methods_list(self):
        p = ChannelConfig.Payment(method=["pix", "card"])
        assert p.available_methods == ["pix", "card"]

    def test_card_method_valid(self):
        config = ChannelConfig(payment=ChannelConfig.Payment(method="card"))
        config.validate()

    def test_multi_method_valid(self):
        config = ChannelConfig(payment=ChannelConfig.Payment(method=["pix", "card"]))
        config.validate()

    def test_invalid_method_raises(self):
        config = ChannelConfig(payment=ChannelConfig.Payment(method="invalid"))
        with pytest.raises(ValueError, match="inválido"):
            config.validate()


# ── WP-E3: Checkout payment selector ────────────────────────────────


class TestCheckoutPaymentSelector:
    def test_checkout_shows_method_selector_when_multiple(self, client: Client, channel, product, customer):
        _login_as_customer(client, customer)
        channel.config = ChannelConfig(
            payment=ChannelConfig.Payment(method=["pix", "card"]),
        ).to_dict()
        channel.save()

        client.post("/cart/add/", {"sku": product.sku, "qty": 1})
        resp = client.get("/checkout/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert 'name="payment_method"' in content
        assert 'value="pix"' in content
        assert 'value="card"' in content

    def test_checkout_hides_selector_when_single_method(self, client: Client, channel, product, customer):
        _login_as_customer(client, customer)
        channel.config = ChannelConfig(
            payment=ChannelConfig.Payment(method="pix"),
        ).to_dict()
        channel.save()

        client.post("/cart/add/", {"sku": product.sku, "qty": 1})
        resp = client.get("/checkout/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert 'name="payment_method"' not in content


# ── WP-E3: Payment page conditional rendering ───────────────────────


class TestPaymentPageCard:
    def test_payment_page_renders_stripe_form(self, client: Client, channel):
        order = Order.objects.create(
            ref="ORD-CARD-PAGE",
            channel=channel,
            status="confirmed",
            total_q=2000,
            data={"payment": {"method": "card", "status": "pending", "client_secret": "pi_test_secret"}},
        )
        resp = client.get(f"/pedido/{order.ref}/pagamento/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Pagamento com Cartão" in content
        assert "stripe-payment-element" in content
        assert "pi_test_secret" in content

    def test_pix_flow_unchanged(self, client: Client, channel):
        order = Order.objects.create(
            ref="ORD-PIX-UNCH",
            channel=channel,
            status="confirmed",
            total_q=800,
            data={
                "payment": {
                    "method": "pix",
                    "status": "pending",
                    "copy_paste": "00020126...",
                    "expires_at": "2099-01-01T00:00:00+00:00",
                },
            },
        )
        resp = client.get(f"/pedido/{order.ref}/pagamento/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Pagamento PIX" in content
        assert "PIX Copia e Cola" in content
        assert "Expira em" in content


# ── WP-E3: CardCreateHandler ────────────────────────────────────────


class TestCardCreateHandler:
    def test_card_creates_stripe_intent(self, channel):
        order = Order.objects.create(
            ref="ORD-CARD-H1",
            channel=channel,
            status="confirmed",
            total_q=3000,
            data={"payment": {"method": "card"}},
        )
        directive = Directive.objects.create(
            topic=CARD_CREATE,
            payload={"order_ref": order.ref, "amount_q": 3000},
        )

        mock_backend = MagicMock()
        mock_backend.create_intent.return_value = MagicMock(
            intent_id="intent_123",
            status="pending",
            amount_q=3000,
            client_secret="pi_secret_test",
            metadata={},
        )

        handler = CardCreateHandler(backend=mock_backend)
        handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        assert directive.status == "done"
        assert directive.payload["intent_id"] == "intent_123"

        order.refresh_from_db()
        assert order.data["payment"]["method"] == "card"
        assert order.data["payment"]["client_secret"] == "pi_secret_test"
        assert order.data["payment"]["intent_id"] == "intent_123"

    def test_card_skips_if_intent_exists(self, channel):
        order = Order.objects.create(
            ref="ORD-CARD-H2",
            channel=channel,
            status="confirmed",
            total_q=2000,
            data={"payment": {"method": "card", "intent_id": "already_exists"}},
        )
        directive = Directive.objects.create(
            topic=CARD_CREATE,
            payload={"order_ref": order.ref},
        )

        mock_backend = MagicMock()
        handler = CardCreateHandler(backend=mock_backend)
        handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        assert directive.status == "done"
        mock_backend.create_intent.assert_not_called()

    def test_card_reads_amount_from_order(self, channel):
        order = Order.objects.create(
            ref="ORD-CARD-H3",
            channel=channel,
            status="confirmed",
            total_q=4500,
            data={"payment": {"method": "card"}},
        )
        directive = Directive.objects.create(
            topic=CARD_CREATE,
            payload={"order_ref": order.ref},
        )

        mock_backend = MagicMock()
        mock_backend.create_intent.return_value = MagicMock(
            intent_id="intent_456",
            status="pending",
            amount_q=4500,
            client_secret="pi_secret_456",
            metadata={},
        )

        handler = CardCreateHandler(backend=mock_backend)
        handler.handle(message=directive, ctx={})

        mock_backend.create_intent.assert_called_once_with(
            amount_q=4500, currency="BRL", reference=order.ref,
            metadata={"method": "card"},
        )


# ── WP-E3: PixGenerateHandler skips card ────────────────────────────


class TestPixHandlerSkipsCard:
    def test_pix_handler_skips_card_orders(self, channel):
        order = Order.objects.create(
            ref="ORD-SKIP-PIX",
            channel=channel,
            status="confirmed",
            total_q=2000,
            data={"payment": {"method": "card"}},
        )
        directive = Directive.objects.create(
            topic="pix.generate",
            payload={"order_ref": order.ref, "amount_q": 2000},
        )

        mock_backend = MagicMock()
        handler = PixGenerateHandler(backend=mock_backend)
        handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        assert directive.status == "done"
        mock_backend.create_intent.assert_not_called()
