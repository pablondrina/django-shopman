"""
Testes do webhook Stripe.

Cobre:
- payment_intent.succeeded → authorize + capture via PaymentService
- payment_intent.payment_failed → fail via PaymentService
- charge.refunded → refund via PaymentService
- Assinatura inválida → 400
- Evento desconhecido → 200 (acknowledge, ignore)
- Integração: webhook → on_payment_confirmed → directives

Todos os testes mocam o stripe SDK (sem credenciais reais).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from shopman.ordering.models import Channel, Directive, Order
from shopman.payments.service import PaymentService

from channels.topics import NOTIFICATION_SEND, STOCK_COMMIT

WEBHOOK_URL = "/api/webhooks/stripe/"

STRIPE_SETTINGS = {
    "SECRET_KEY": "sk_test_fake",
    "WEBHOOK_SECRET": "whsec_test_fake",
}


def _make_channel(**overrides) -> Channel:
    """Cria canal com config de pagamento Stripe."""
    config = {
        "confirmation": {
            "mode": "optimistic",
            "timeout_minutes": 5,
        },
        "payment": {
            "method": "card",
            "timeout_minutes": 10,
        },
        "stock": {
            "hold_ttl_minutes": 20,
            "safety_margin": 2,
        },
        "pipeline": {
            "on_commit": ["customer.ensure", "stock.hold"],
            "on_confirmed": ["notification.send:order_confirmed"],
            "on_payment_confirmed": ["stock.commit", "notification.send:payment_confirmed"],
            "on_cancelled": ["notification.send:order_cancelled"],
        },
        "notifications": {
            "backend": "console",
        },
        "flow": {
            "initial_status": "new",
            "transitions": {
                "new": ["confirmed", "cancelled"],
                "confirmed": ["processing", "cancelled"],
                "processing": ["ready", "cancelled"],
                "ready": ["dispatched", "completed"],
                "dispatched": ["delivered"],
                "delivered": ["completed"],
                "completed": [],
                "cancelled": [],
            },
            "terminal_statuses": ["completed", "cancelled"],
            "auto_transitions": {
                "on_payment_confirm": "confirmed",
            },
        },
    }
    config.update(overrides.pop("config", {}))
    defaults = dict(ref="web-stripe", name="Web (Stripe)", config=config)
    defaults.update(overrides)
    return Channel.objects.create(**defaults)


def _make_order(channel: Channel, ref: str = "ORD-ST-001", total_q: int = 5000, **kwargs) -> Order:
    return Order.objects.create(
        ref=ref,
        channel=channel,
        total_q=total_q,
        status=kwargs.pop("status", Order.Status.CONFIRMED),
        data=kwargs.pop("data", {}),
        **kwargs,
    )


def _build_stripe_event(event_type: str, data_object: dict) -> MagicMock:
    """Build a mock Stripe Event object."""
    event = MagicMock()
    event.type = event_type

    # Use a SimpleNamespace-like MagicMock for the data object
    obj = MagicMock()
    for key, value in data_object.items():
        setattr(obj, key, value)

    event.data.object = obj
    return event


@override_settings(SHOPMAN_STRIPE=STRIPE_SETTINGS)
class StripeWebhookSucceededTests(TestCase):
    """payment_intent.succeeded → authorize + capture."""

    def setUp(self):
        self.client = APIClient()
        self.channel = _make_channel()

    @patch("channels.backends.payment_stripe.StripeBackend._get_stripe")
    def test_succeeded_authorizes_and_captures(self, mock_get_stripe):
        """payment_intent.succeeded → PaymentService.authorize + capture."""
        intent = PaymentService.create_intent(
            order_ref="ORD-ST-001",
            amount_q=5000,
            method="card",
            gateway="stripe",
            gateway_id="pi_test_123",
        )

        order = _make_order(
            self.channel,
            ref="ORD-ST-001",
            total_q=5000,
            data={"payment": {"intent_id": intent.ref, "status": "pending"}},
        )

        event = _build_stripe_event("payment_intent.succeeded", {
            "id": "pi_test_123",
            "metadata": {"shopman_ref": intent.ref},
        })

        mock_stripe = MagicMock()
        mock_stripe.Webhook.construct_event.return_value = event
        mock_get_stripe.return_value = mock_stripe

        response = self.client.post(
            WEBHOOK_URL,
            data=b'{"type":"payment_intent.succeeded"}',
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=123,v1=fakesig",
        )

        self.assertEqual(response.status_code, 200)

        intent.refresh_from_db()
        self.assertEqual(intent.status, "captured")

        order.refresh_from_db()
        self.assertEqual(order.data["payment"]["status"], "captured")

    @patch("channels.backends.payment_stripe.StripeBackend._get_stripe")
    def test_succeeded_creates_notification_directive(self, mock_get_stripe):
        """payment_intent.succeeded → notification.send directive."""
        intent = PaymentService.create_intent(
            order_ref="ORD-ST-NOTIF",
            amount_q=2500,
            method="card",
            gateway="stripe",
            gateway_id="pi_notif",
        )

        _make_order(
            self.channel,
            ref="ORD-ST-NOTIF",
            total_q=2500,
            data={"payment": {"intent_id": intent.ref, "status": "pending"}},
        )

        event = _build_stripe_event("payment_intent.succeeded", {
            "id": "pi_notif",
            "metadata": {"shopman_ref": intent.ref},
        })

        mock_stripe = MagicMock()
        mock_stripe.Webhook.construct_event.return_value = event
        mock_get_stripe.return_value = mock_stripe

        self.client.post(
            WEBHOOK_URL,
            data=b'{}',
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=123,v1=fakesig",
        )

        notif = Directive.objects.filter(
            topic=NOTIFICATION_SEND,
            payload__template="payment_confirmed",
        ).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.payload["order_ref"], "ORD-ST-NOTIF")

    @patch("channels.backends.payment_stripe.StripeBackend._get_stripe")
    def test_succeeded_creates_stock_commit_when_holds_exist(self, mock_get_stripe):
        """payment_intent.succeeded with holds → stock.commit directive."""
        intent = PaymentService.create_intent(
            order_ref="ORD-ST-HOLD",
            amount_q=3000,
            method="card",
            gateway="stripe",
            gateway_id="pi_hold",
        )

        _make_order(
            self.channel,
            ref="ORD-ST-HOLD",
            total_q=3000,
            data={
                "payment": {"intent_id": intent.ref, "status": "pending"},
                "holds": [
                    {"hold_id": "h1", "sku": "BAGUETE", "qty": 2.0},
                ],
            },
        )

        event = _build_stripe_event("payment_intent.succeeded", {
            "id": "pi_hold",
            "metadata": {"shopman_ref": intent.ref},
        })

        mock_stripe = MagicMock()
        mock_stripe.Webhook.construct_event.return_value = event
        mock_get_stripe.return_value = mock_stripe

        self.client.post(
            WEBHOOK_URL,
            data=b'{}',
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=123,v1=fakesig",
        )

        commit = Directive.objects.filter(topic=STOCK_COMMIT).first()
        self.assertIsNotNone(commit)
        self.assertEqual(commit.payload["order_ref"], "ORD-ST-HOLD")


@override_settings(SHOPMAN_STRIPE=STRIPE_SETTINGS)
class StripeWebhookFailedTests(TestCase):
    """payment_intent.payment_failed → fail."""

    def setUp(self):
        self.client = APIClient()

    @patch("channels.backends.payment_stripe.StripeBackend._get_stripe")
    def test_payment_failed_marks_intent_failed(self, mock_get_stripe):
        """payment_intent.payment_failed → PaymentService.fail."""
        intent = PaymentService.create_intent(
            order_ref="ORD-ST-FAIL",
            amount_q=1500,
            method="card",
            gateway="stripe",
            gateway_id="pi_fail",
        )

        last_error = MagicMock()
        last_error.code = "card_declined"
        last_error.message = "Your card was declined."

        event = _build_stripe_event("payment_intent.payment_failed", {
            "id": "pi_fail",
            "metadata": {"shopman_ref": intent.ref},
            "last_payment_error": last_error,
        })

        mock_stripe = MagicMock()
        mock_stripe.Webhook.construct_event.return_value = event
        mock_get_stripe.return_value = mock_stripe

        response = self.client.post(
            WEBHOOK_URL,
            data=b'{}',
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=123,v1=fakesig",
        )

        self.assertEqual(response.status_code, 200)

        intent.refresh_from_db()
        self.assertEqual(intent.status, "failed")
        self.assertEqual(intent.gateway_data.get("error_code"), "card_declined")


@override_settings(SHOPMAN_STRIPE=STRIPE_SETTINGS)
class StripeWebhookRefundedTests(TestCase):
    """charge.refunded → refund."""

    def setUp(self):
        self.client = APIClient()

    @patch("channels.backends.payment_stripe.StripeBackend._get_stripe")
    def test_charge_refunded_creates_refund(self, mock_get_stripe):
        """charge.refunded → PaymentService.refund."""
        intent = PaymentService.create_intent(
            order_ref="ORD-ST-REFUND",
            amount_q=4000,
            method="card",
            gateway="stripe",
            gateway_id="pi_refund",
        )
        # Move through authorize → capture so refund is valid
        PaymentService.authorize(intent.ref, gateway_id="pi_refund")
        PaymentService.capture(intent.ref, gateway_id="pi_refund")

        event = _build_stripe_event("charge.refunded", {
            "id": "ch_refund_123",
            "payment_intent": "pi_refund",
            "amount_refunded": 4000,
        })

        mock_stripe = MagicMock()
        mock_stripe.Webhook.construct_event.return_value = event
        mock_get_stripe.return_value = mock_stripe

        response = self.client.post(
            WEBHOOK_URL,
            data=b'{}',
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=123,v1=fakesig",
        )

        self.assertEqual(response.status_code, 200)

        intent.refresh_from_db()
        self.assertEqual(intent.status, "refunded")

        refunded_q = PaymentService.refunded_total(intent.ref)
        self.assertEqual(refunded_q, 4000)


@override_settings(SHOPMAN_STRIPE=STRIPE_SETTINGS)
class StripeWebhookSignatureTests(TestCase):
    """Signature verification."""

    def setUp(self):
        self.client = APIClient()

    @patch("channels.backends.payment_stripe.StripeBackend._get_stripe")
    def test_invalid_signature_returns_400(self, mock_get_stripe):
        """Invalid Stripe signature → 400."""
        mock_stripe = MagicMock()
        mock_stripe.Webhook.construct_event.side_effect = ValueError(
            "Invalid signature"
        )
        mock_get_stripe.return_value = mock_stripe

        response = self.client.post(
            WEBHOOK_URL,
            data=b'{"type":"payment_intent.succeeded"}',
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=123,v1=badsig",
        )

        self.assertEqual(response.status_code, 400)

    def test_missing_signature_header_returns_400(self):
        """No Stripe-Signature header → 400."""
        response = self.client.post(
            WEBHOOK_URL,
            data=b'{"type":"payment_intent.succeeded"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)


@override_settings(SHOPMAN_STRIPE=STRIPE_SETTINGS)
class StripeWebhookUnknownEventTests(TestCase):
    """Unknown event types → 200 (acknowledge, ignore)."""

    def setUp(self):
        self.client = APIClient()

    @patch("channels.backends.payment_stripe.StripeBackend._get_stripe")
    def test_unknown_event_returns_200(self, mock_get_stripe):
        """Unknown event type → 200 OK, no side effects."""
        event = _build_stripe_event("customer.created", {
            "id": "cus_123",
            "metadata": {},
        })

        mock_stripe = MagicMock()
        mock_stripe.Webhook.construct_event.return_value = event
        mock_get_stripe.return_value = mock_stripe

        response = self.client.post(
            WEBHOOK_URL,
            data=b'{}',
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=123,v1=fakesig",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Directive.objects.count(), 0)
