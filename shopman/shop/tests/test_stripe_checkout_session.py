"""WP-GAP-02 — Stripe Checkout (hosted redirect) coverage.

Covers:
- payment.initiate(method="card") persists checkout_url in order.data["payment"]
- adapter.create_intent calls stripe.checkout.Session.create with the right
  success_url / cancel_url / metadata.
- Webhook event "checkout.session.completed" → PaymentIntent captured + dispatch
  on_paid.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from shopman.orderman.ids import generate_idempotency_key, generate_session_key
from shopman.orderman.models import Order, Session
from shopman.orderman.services.commit import CommitService
from shopman.orderman.services.modify import ModifyService
from shopman.payman import PaymentService

from shopman.shop.models import Channel

STRIPE_SETTINGS = {
    "secret_key": "sk_test_fake",
    "webhook_secret": "whsec_test_fake",
    "capture_method": "automatic",
    "domain": "https://shop.example.com",
}

PAYMENT_ADAPTERS_STRIPE_CARD = {
    "pix": "shopman.shop.adapters.payment_mock",
    "card": "shopman.shop.adapters.payment_stripe",
}


def _commit_card_order(channel_ref: str = "web") -> Order:
    """Helper: commit an order with payment.method=card."""
    session_key = generate_session_key()
    Session.objects.create(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
        pricing_policy="fixed",
        edit_policy="open",
        handle_type="guest",
        handle_ref="test-guest",
        data={"origin_channel": "web"},
    )
    ModifyService.modify_session(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=[
            {"op": "add_line", "sku": "TEST-SKU", "qty": 1, "unit_price_q": 1000},
            {"op": "set_data", "path": "payment.method", "value": "card"},
            {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
        ],
        ctx={"actor": "test"},
    )
    result = CommitService.commit(
        session_key=session_key,
        channel_ref=channel_ref,
        idempotency_key=generate_idempotency_key(),
        ctx={"actor": "test"},
    )
    return Order.objects.get(ref=result["order_ref"])


# ══════════════════════════════════════════════════════════════
# adapter.create_intent — Stripe Checkout Session
# ══════════════════════════════════════════════════════════════


@override_settings(
    SHOPMAN_STRIPE=STRIPE_SETTINGS,
    SHOPMAN_PAYMENT_ADAPTERS=PAYMENT_ADAPTERS_STRIPE_CARD,
)
class StripeCreateIntentTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Channel.objects.create(ref="web", name="Web", is_active=True)

    def _mock_session(self, *, session_id="cs_test_abc", url="https://checkout.stripe.com/c/pay/cs_test_abc"):
        session = MagicMock()
        session.id = session_id
        session.url = url
        session.payment_intent = None
        return session

    def test_create_intent_calls_stripe_checkout_session(self) -> None:
        order = _commit_card_order()
        from shopman.shop.adapters import payment_stripe

        with patch.object(payment_stripe, "_get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            mock_session = self._mock_session()
            mock_stripe.checkout.Session.create.return_value = mock_session
            mock_get_stripe.return_value = mock_stripe

            intent = payment_stripe.create_intent(
                order_ref=order.ref,
                amount_q=order.total_q,
                currency="BRL",
                method="card",
                metadata={"method": "card"},
            )

        # Stripe was called with a Checkout Session payload (NOT PaymentIntent).
        mock_stripe.checkout.Session.create.assert_called_once()
        kwargs = mock_stripe.checkout.Session.create.call_args.kwargs
        assert kwargs["mode"] == "payment"
        assert kwargs["payment_method_types"] == ["card"]
        assert kwargs["success_url"] == f"https://shop.example.com/pedido/{order.ref}/confirmacao/"
        assert kwargs["cancel_url"] == f"https://shop.example.com/pedido/{order.ref}/pagamento/"
        assert kwargs["metadata"]["order_ref"] == order.ref
        assert kwargs["metadata"]["shopman_ref"] == intent.intent_ref
        line_item = kwargs["line_items"][0]
        assert line_item["price_data"]["currency"] == "brl"
        assert line_item["price_data"]["unit_amount"] == order.total_q

        # The adapter must NOT call stripe.PaymentIntent.create — Checkout Session
        # is now the only path.
        mock_stripe.PaymentIntent.create.assert_not_called()

        # The returned intent carries the hosted URL in metadata.
        assert intent.metadata["checkout_url"] == "https://checkout.stripe.com/c/pay/cs_test_abc"

    def test_initiate_persists_checkout_url_on_order(self) -> None:
        # Create an order *outside* the lifecycle so payment.initiate isn't
        # auto-triggered during commit. We're testing the orchestrator-side
        # persistence of `checkout_url`, not the lifecycle wiring.
        order = Order.objects.create(
            ref="ORD-CARD-INIT-001",
            channel_ref="web",
            status="new",
            total_q=1500,
            handle_type="phone",
            handle_ref="5543000000001",
            data={"payment": {"method": "card"}},
        )
        from shopman.shop.adapters import payment_stripe
        from shopman.shop.services import payment as payment_svc

        with patch.object(payment_stripe, "_get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            mock_stripe.checkout.Session.create.return_value = self._mock_session(
                session_id="cs_test_persist",
                url="https://checkout.stripe.com/c/pay/cs_test_persist",
            )
            mock_get_stripe.return_value = mock_stripe

            payment_svc.initiate(order)

        order.refresh_from_db()
        payment_data = order.data["payment"]
        assert payment_data["method"] == "card"
        assert payment_data["checkout_url"] == "https://checkout.stripe.com/c/pay/cs_test_persist"
        # Hosted redirect ⇒ we never expose a client_secret.
        assert "client_secret" not in payment_data


# ══════════════════════════════════════════════════════════════
# Webhook — checkout.session.completed
# ══════════════════════════════════════════════════════════════


@override_settings(
    SHOPMAN_STRIPE=STRIPE_SETTINGS,
    SHOPMAN_PAYMENT_ADAPTERS=PAYMENT_ADAPTERS_STRIPE_CARD,
)
class StripeCheckoutSessionWebhookTests(TestCase):
    URL = "/api/webhooks/stripe/"

    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        Channel.objects.create(ref="web", name="Web", is_active=True)

    def _mock_event(self, *, shopman_ref: str, payment_intent_id: str | None, session_id: str = "cs_test_xyz"):
        mock_event = MagicMock()
        mock_event.type = "checkout.session.completed"
        session = MagicMock()
        session.id = session_id
        session.payment_intent = payment_intent_id
        session.metadata = {"shopman_ref": shopman_ref}
        mock_event.data.object = session
        return mock_event

    def _post(self, mock_event) -> object:
        with patch("shopman.shop.adapters.payment_stripe._get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            mock_stripe.Webhook.construct_event.return_value = mock_event
            mock_get_stripe.return_value = mock_stripe
            return self.client.post(
                self.URL,
                data=json.dumps({"type": "checkout.session.completed"}).encode(),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="valid-sig",
            )

    def test_checkout_session_completed_captures_intent(self) -> None:
        order = _commit_card_order()
        intent = PaymentService.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="card",
            gateway="stripe",
            gateway_data={},
        )
        intent.gateway_id = "cs_test_xyz"
        intent.save(update_fields=["gateway_id"])
        order.data["payment"] = {
            "method": "card",
            "intent_ref": intent.ref,
            "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_xyz",
        }
        order.save(update_fields=["data", "updated_at"])

        resp = self._post(self._mock_event(
            shopman_ref=intent.ref,
            payment_intent_id="pi_test_promoted",
        ))
        assert resp.status_code == 200, getattr(resp, "data", resp.content)

        intent.refresh_from_db()
        assert intent.status == "captured"
        # gateway_id was promoted from session id to payment_intent id.
        assert intent.gateway_id == "pi_test_promoted"

    def test_checkout_session_without_payment_intent_still_captures(self) -> None:
        """Some Checkout Sessions complete with payment_intent=None (e.g. zero-decimal currencies);
        we must still capture using the session id as gateway anchor."""
        order = _commit_card_order()
        intent = PaymentService.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="card",
            gateway="stripe",
            gateway_data={},
        )
        intent.gateway_id = "cs_test_no_pi"
        intent.save(update_fields=["gateway_id"])
        order.data["payment"] = {"method": "card", "intent_ref": intent.ref}
        order.save(update_fields=["data", "updated_at"])

        resp = self._post(self._mock_event(
            shopman_ref=intent.ref,
            payment_intent_id=None,
            session_id="cs_test_no_pi",
        ))
        assert resp.status_code == 200

        intent.refresh_from_db()
        assert intent.status == "captured"

    def test_checkout_session_completed_dispatches_on_paid(self) -> None:
        """Webhook must invoke the lifecycle dispatch so downstream handlers fire."""
        order = _commit_card_order()
        intent = PaymentService.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="card",
            gateway="stripe",
            gateway_data={},
        )
        intent.gateway_id = "cs_test_dispatch"
        intent.save(update_fields=["gateway_id"])
        order.data["payment"] = {"method": "card", "intent_ref": intent.ref}
        order.save(update_fields=["data", "updated_at"])

        with patch("shopman.shop.lifecycle.dispatch") as mock_dispatch:
            self._post(self._mock_event(
                shopman_ref=intent.ref,
                payment_intent_id="pi_dispatch",
                session_id="cs_test_dispatch",
            ))

        # dispatch(order, "on_paid") must have fired exactly once.
        assert mock_dispatch.called
        called_phases = [c.args[1] for c in mock_dispatch.call_args_list if len(c.args) >= 2]
        assert "on_paid" in called_phases
