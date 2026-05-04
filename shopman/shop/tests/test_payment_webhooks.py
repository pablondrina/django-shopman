"""
Tests for payment webhooks — Stripe and EFI/PIX.

Covers:
- Stripe happy path (payment_intent.succeeded → order confirmed)
- EFI/PIX happy path (pix notification → order confirmed)
- Idempotency (duplicate webhook = single state change)
- Race condition (payment after cancellation → graceful handling)
- Invalid signature → 400
- Order not found → graceful ignore
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from shopman.orderman.ids import generate_idempotency_key, generate_session_key
from shopman.orderman.models import IdempotencyKey, Order, Session
from shopman.orderman.services.commit import CommitService
from shopman.orderman.services.modify import ModifyService
from shopman.payman import PaymentService

from shopman.shop.models import Channel

STRIPE_SETTINGS = {
    "SECRET_KEY": "sk_test_fake",
    "WEBHOOK_SECRET": "whsec_test_fake",
    "CAPTURE_METHOD": "automatic",
}

EFI_WEBHOOK_SETTINGS = {
    "webhook_token": "test-efi-token",
}


def _create_order_with_payment(channel_ref: str = "web", payment_method: str = "card") -> Order:
    """Helper: create a committed order with a payment intent."""
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
            {"op": "set_data", "path": "payment.method", "value": payment_method},
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
    return Order.objects.get(ref=result.order_ref)


def _create_pix_intent(order: Order) -> object:
    """Create a PIX PaymentIntent attached to the order."""
    intent = PaymentService.create_intent(
        order_ref=order.ref,
        amount_q=order.total_q,
        method="pix",
        gateway="efi",
        gateway_data={},
    )
    intent.gateway_id = "txid_test_abc123"
    intent.save(update_fields=["gateway_id"])
    # Link intent to order
    order.data.setdefault("payment", {})["intent_ref"] = intent.ref
    order.save(update_fields=["data", "updated_at"])
    return intent


def _create_card_intent(order: Order, stripe_pi_id: str = "pi_test_stripe_abc") -> object:
    """Create a card PaymentIntent attached to the order."""
    intent = PaymentService.create_intent(
        order_ref=order.ref,
        amount_q=order.total_q,
        method="card",
        gateway="stripe",
        gateway_data={},
    )
    intent.gateway_id = stripe_pi_id
    intent.save(update_fields=["gateway_id"])
    order.data.setdefault("payment", {})["intent_ref"] = intent.ref
    order.save(update_fields=["data", "updated_at"])
    return intent


# ══════════════════════════════════════════════════════════════
# Fixtures / setUp helpers
# ══════════════════════════════════════════════════════════════


class WebhookTestBase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        self.web_channel = Channel.objects.create(
            ref="web",
            name="Web",
            is_active=True,
        )


# ══════════════════════════════════════════════════════════════
# Stripe Webhook Tests
# ══════════════════════════════════════════════════════════════


@override_settings(SHOPMAN_STRIPE=STRIPE_SETTINGS)
class StripeWebhookTests(WebhookTestBase):
    """Tests for /api/webhooks/stripe/."""

    URL = "/api/webhooks/stripe/"

    def _make_event(self, event_type: str, stripe_pi_id: str, shopman_ref: str) -> dict:
        """Build a minimal Stripe webhook event payload."""
        return {
            "type": event_type,
            "data": {
                "object": {
                    "id": stripe_pi_id,
                    "object": "payment_intent",
                    "status": "succeeded",
                    "amount": 1000,
                    "currency": "brl",
                    "metadata": {
                        "shopman_ref": shopman_ref,
                        "order_ref": "ORD-TEST",
                    },
                    "last_payment_error": None,
                }
            },
        }

    def _post_webhook(self, event: dict, sig: str = "valid-sig") -> object:
        payload = json.dumps(event).encode()
        return self.client.post(
            self.URL,
            data=payload,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=sig,
        )

    def _mock_stripe_construct(self, event_dict: dict):
        """Return a mock Stripe Event object matching event_dict."""
        mock_event = MagicMock()
        mock_event.type = event_dict["type"]
        obj = event_dict["data"]["object"]
        mock_pi = MagicMock()
        mock_pi.id = obj["id"]
        mock_pi.status = obj["status"]
        mock_pi.metadata = obj["metadata"]
        mock_pi.last_payment_error = obj.get("last_payment_error")
        mock_event.data.object = mock_pi
        return mock_event

    # ── Happy path ────────────────────────────────────────────

    def test_stripe_payment_succeeded_captures_intent(self) -> None:
        """payment_intent.succeeded → PaymentIntent captured."""
        order = _create_order_with_payment("web", "card")
        intent = _create_card_intent(order)
        event_dict = self._make_event("payment_intent.succeeded", intent.gateway_id, intent.ref)

        mock_event = self._mock_stripe_construct(event_dict)
        with patch("shopman.shop.adapters.payment_stripe._get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            mock_stripe.Webhook.construct_event.return_value = mock_event
            mock_get_stripe.return_value = mock_stripe

            resp = self._post_webhook(event_dict)

        self.assertEqual(resp.status_code, 200, resp.data)

        # Intent should be captured
        intent.refresh_from_db()
        self.assertEqual(intent.status, "captured")

    def test_stripe_payment_succeeded_captures_payman_intent(self) -> None:
        """payment_intent.succeeded → Payman intent.status == 'captured'.

        Status is NOT written to order.data["payment"] — Payman is the canonical source.
        """
        order = _create_order_with_payment("web", "card")
        intent = _create_card_intent(order)
        event_dict = self._make_event("payment_intent.succeeded", intent.gateway_id, intent.ref)
        mock_event = self._mock_stripe_construct(event_dict)

        with patch("shopman.shop.adapters.payment_stripe._get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            mock_stripe.Webhook.construct_event.return_value = mock_event
            mock_get_stripe.return_value = mock_stripe

            self._post_webhook(event_dict)

        intent.refresh_from_db()
        self.assertEqual(intent.status, "captured")
        order.refresh_from_db()
        self.assertNotIn("status", order.data.get("payment", {}))

    # ── Idempotency ───────────────────────────────────────────

    def test_stripe_duplicate_webhook_idempotent(self) -> None:
        """Same webhook twice → PaymentIntent captured once, downstream hook once."""
        order = _create_order_with_payment("web", "card")
        intent = _create_card_intent(order)
        event_dict = self._make_event("payment_intent.succeeded", intent.gateway_id, intent.ref)
        mock_event = self._mock_stripe_construct(event_dict)

        with patch("shopman.shop.adapters.payment_stripe._get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            mock_stripe.Webhook.construct_event.return_value = mock_event
            mock_get_stripe.return_value = mock_stripe

            with patch(
                "shopman.shop.webhooks.stripe.StripeWebhookView._trigger_order_hooks"
            ) as mock_hooks:
                resp1 = self._post_webhook(event_dict)
                resp2 = self._post_webhook(event_dict)

        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(mock_hooks.call_count, 1)
        self.assertEqual(IdempotencyKey.objects.filter(scope="webhook:stripe").count(), 1)

        # Status still captured (not double-captured)
        intent.refresh_from_db()
        self.assertEqual(intent.status, "captured")

    # ── Race condition ────────────────────────────────────────

    def test_stripe_payment_after_cancel_handled_gracefully(self) -> None:
        """Webhook for cancelled order → no crash, returns 200."""

        order = _create_order_with_payment("web", "card")
        intent = _create_card_intent(order)

        # Cancel the order before payment arrives
        order.transition_status("cancelled", actor="test")

        event_dict = self._make_event("payment_intent.succeeded", intent.gateway_id, intent.ref)
        mock_event = self._mock_stripe_construct(event_dict)

        with patch("shopman.shop.adapters.payment_stripe._get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            mock_stripe.Webhook.construct_event.return_value = mock_event
            mock_get_stripe.return_value = mock_stripe

            resp = self._post_webhook(event_dict)

        # Should not crash
        self.assertEqual(resp.status_code, 200)

    # ── Invalid signature ─────────────────────────────────────

    def test_stripe_missing_signature_returns_400(self) -> None:
        """Request without Stripe-Signature header → 400."""
        resp = self.client.post(
            self.URL,
            data=b'{"type": "test"}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_stripe_invalid_signature_returns_400(self) -> None:
        """Request with invalid Stripe-Signature → 400."""
        with patch("shopman.shop.adapters.payment_stripe._get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            mock_stripe.Webhook.construct_event.side_effect = Exception("Signature invalid")
            mock_get_stripe.return_value = mock_stripe

            resp = self._post_webhook({"type": "test"}, sig="bad-sig")

        self.assertEqual(resp.status_code, 400)

    # ── Unconfigured ──────────────────────────────────────────

    @override_settings(SHOPMAN_STRIPE={})
    def test_stripe_webhook_not_configured_returns_500(self) -> None:
        """No WEBHOOK_SECRET configured → 500."""
        resp = self._post_webhook({"type": "test"}, sig="any-sig")
        self.assertEqual(resp.status_code, 500)


# ══════════════════════════════════════════════════════════════
# EFI PIX Webhook Tests
# ══════════════════════════════════════════════════════════════


@override_settings(SHOPMAN_EFI_WEBHOOK=EFI_WEBHOOK_SETTINGS)
class EfiPixWebhookTests(WebhookTestBase):
    """Tests for /api/webhooks/efi/pix/."""

    URL = "/api/webhooks/efi/pix/"
    AUTH_HEADER = {"HTTP_X_EFI_WEBHOOK_TOKEN": "test-efi-token"}

    def _post(self, payload: dict, **headers) -> object:
        combined = {**self.AUTH_HEADER, **headers}
        return self.client.post(self.URL, payload, format="json", **combined)

    # ── GET health check ──────────────────────────────────────

    def test_efi_get_health_check(self) -> None:
        """GET /webhook/efi-pix/ → 200 (health check for EFI)."""
        resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 200)

    # ── Happy path ────────────────────────────────────────────

    def test_efi_pix_payment_captures_intent(self) -> None:
        """PIX notification → PaymentIntent captured."""
        order = _create_order_with_payment("web", "pix")
        intent = _create_pix_intent(order)

        payload = {
            "pix": [
                {
                    "txid": intent.gateway_id,
                    "endToEndId": "E1234567890",
                    "valor": f"{order.total_q / 100:.2f}",
                }
            ]
        }

        resp = self._post(payload)
        self.assertEqual(resp.status_code, 200, resp.data)

        intent.refresh_from_db()
        self.assertEqual(intent.status, "captured")

    def test_efi_pix_payment_records_e2e_id(self) -> None:
        """PIX notification → order.data['payment']['e2e_id'] recorded, Payman intent captured.

        Status is NOT written to order.data["payment"] — Payman is the canonical source.
        """
        order = _create_order_with_payment("web", "pix")
        intent = _create_pix_intent(order)

        payload = {
            "pix": [
                {
                    "txid": intent.gateway_id,
                    "endToEndId": "E9999999999",
                    "valor": "10.00",
                }
            ]
        }
        self._post(payload)

        order.refresh_from_db()
        self.assertEqual(order.data.get("payment", {}).get("e2e_id"), "E9999999999")
        self.assertNotIn("status", order.data.get("payment", {}))
        intent.refresh_from_db()
        self.assertEqual(intent.status, "captured")

    # ── Idempotency ───────────────────────────────────────────

    def test_efi_duplicate_webhook_idempotent(self) -> None:
        """Same PIX notification twice → intent captured once."""
        order = _create_order_with_payment("web", "pix")
        intent = _create_pix_intent(order)

        payload = {
            "pix": [
                {
                    "txid": intent.gateway_id,
                    "endToEndId": "E_IDEM_TEST",
                    "valor": "10.00",
                }
            ]
        }

        resp1 = self._post(payload)
        resp2 = self._post(payload)

        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp1.data["processed"], 1)
        self.assertEqual(resp2.data["replays"], 1)
        self.assertEqual(IdempotencyKey.objects.filter(scope="webhook:efi-pix").count(), 1)

        intent.refresh_from_db()
        self.assertEqual(intent.status, "captured")

    def test_efi_same_e2e_cannot_capture_another_txid(self) -> None:
        """A replayed PIX e2e id is global, not scoped only to a txid."""
        order_1 = _create_order_with_payment("web", "pix")
        intent_1 = _create_pix_intent(order_1)
        order_2 = _create_order_with_payment("web", "pix")
        intent_2 = PaymentService.create_intent(
            order_ref=order_2.ref,
            amount_q=order_2.total_q,
            method="pix",
            gateway="efi",
            gateway_data={},
        )
        intent_2.gateway_id = "txid_second_order"
        intent_2.save(update_fields=["gateway_id"])
        order_2.data.setdefault("payment", {})["intent_ref"] = intent_2.ref
        order_2.save(update_fields=["data", "updated_at"])

        e2e_id = "E_GLOBAL_REPLAY"
        resp1 = self._post(
            {"pix": [{"txid": intent_1.gateway_id, "endToEndId": e2e_id, "valor": "10.00"}]}
        )
        resp2 = self._post(
            {"pix": [{"txid": intent_2.gateway_id, "endToEndId": e2e_id, "valor": "10.00"}]}
        )

        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.data["replays"], 1)
        intent_2.refresh_from_db()
        self.assertEqual(intent_2.status, "pending")

    def test_efi_in_progress_replay_returns_409(self) -> None:
        from shopman.shop.services.webhook_idempotency import stable_webhook_key

        IdempotencyKey.objects.create(
            scope="webhook:efi-pix",
            key=f"txid:{stable_webhook_key('txid_busy')}",
            status="in_progress",
        )

        resp = self._post(
            {"pix": [{"txid": "txid_busy", "endToEndId": "", "valor": "10.00"}]}
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["in_progress"], 1)

    def test_confirm_pix_without_e2e_is_still_order_idempotent(self) -> None:
        """Legacy callers without e2e_id must not dispatch on_paid twice."""
        from shopman.shop.services.pix_confirmation import confirm_pix

        order = _create_order_with_payment("web", "pix")
        intent = _create_pix_intent(order)

        with patch("shopman.shop.lifecycle.dispatch") as mock_dispatch:
            confirm_pix(txid=intent.gateway_id, valor="10.00")
            confirm_pix(txid=intent.gateway_id, valor="10.00")

        self.assertEqual(mock_dispatch.call_count, 1)

    # ── Race condition ────────────────────────────────────────

    def test_efi_payment_after_cancel_handled_gracefully(self) -> None:
        """PIX notification for cancelled order → no crash, 200."""
        order = _create_order_with_payment("web", "pix")
        intent = _create_pix_intent(order)
        order.transition_status("cancelled", actor="test")

        payload = {
            "pix": [
                {
                    "txid": intent.gateway_id,
                    "endToEndId": "E_RACE",
                    "valor": "10.00",
                }
            ]
        }
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 200)

    # ── Order not found ───────────────────────────────────────

    def test_efi_unknown_txid_ignored_gracefully(self) -> None:
        """PIX notification for unknown txid → 200, no crash."""
        payload = {
            "pix": [
                {
                    "txid": "nonexistent_txid_xyz",
                    "endToEndId": "E_UNKNOWN",
                    "valor": "50.00",
                }
            ]
        }
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 200)

    # ── Missing pix data ──────────────────────────────────────

    def test_efi_empty_pix_list_returns_400(self) -> None:
        """POST with empty pix list → 400."""
        resp = self._post({"pix": []})
        self.assertEqual(resp.status_code, 400)

    def test_efi_missing_pix_field_returns_400(self) -> None:
        """POST without pix key → 400."""
        resp = self._post({"other": "data"})
        self.assertEqual(resp.status_code, 400)

    # ── Auth ──────────────────────────────────────────────────

    def test_efi_invalid_token_returns_401(self) -> None:
        """Request with wrong token → 401."""
        resp = self.client.post(
            self.URL,
            {"pix": [{"txid": "abc", "endToEndId": "E1", "valor": "10.00"}]},
            format="json",
            HTTP_X_EFI_WEBHOOK_TOKEN="wrong-token",
        )
        self.assertEqual(resp.status_code, 401)

    def test_efi_missing_token_returns_401(self) -> None:
        """Request without any token → 401."""
        resp = self.client.post(
            self.URL,
            {"pix": [{"txid": "abc", "endToEndId": "E1", "valor": "10.00"}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)

    @override_settings(SHOPMAN_EFI_WEBHOOK={"webhook_token": ""})
    def test_efi_unconfigured_token_rejects_all_requests(self) -> None:
        """Unconfigured webhook_token → every request is rejected, including
        ones that would otherwise match. There is no bypass path."""
        resp = self.client.post(
            self.URL,
            {"pix": [{"txid": "abc", "endToEndId": "E1", "valor": "10.00"}]},
            format="json",
            HTTP_X_EFI_WEBHOOK_TOKEN="any-token",
        )
        self.assertEqual(resp.status_code, 401)
