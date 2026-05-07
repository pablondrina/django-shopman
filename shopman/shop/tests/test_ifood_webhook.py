"""Tests for the real iFood marketplace webhook.

Covers the four cases called out in WP-GAP-01:

* valid token → 200 + ``Order`` created (real :func:`ifood_ingest.ingest`
  path).
* missing / wrong token → 403 with no side effects.
* replay of the same ``order_id`` → 200 ``already_processed`` with no
  duplicate Order.
* malformed payload (no ``order_id``) → 400.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from shopman.orderman.models import IdempotencyKey, Order

from shopman.shop.models import Channel

IFOOD_WEBHOOK_SETTINGS = {
    "webhook_token": "test-ifood-token",
    "merchant_id": "mock-merchant",
}

URL = "/api/webhooks/ifood/"


def _payload(order_id: str = "IFOOD-TEST-001") -> dict:
    return {
        "order_id": order_id,
        "merchant_id": "mock-merchant",
        "status": "PLACED",
        "total": 1500,
        "created_at": "2026-04-18T12:00:00Z",
        "customer": {"name": "Cliente Teste", "phone": "+5543999999999"},
        "delivery": {"type": "DELIVERY", "address": "Rua Teste, 123"},
        "items": [
            {"sku": "PAO-FERMENT", "name": "Pão", "qty": 2, "unit_price_q": 750},
        ],
        "notes": "sem cebola",
    }


@override_settings(SHOPMAN_IFOOD=IFOOD_WEBHOOK_SETTINGS)
class IFoodWebhookAuthTests(TestCase):
    """Auth layer: header, query, wrong token, missing token."""

    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        Channel.objects.get_or_create(
            ref="ifood", defaults={"name": "iFood", "is_active": True}
        )

    def test_missing_token_returns_403(self) -> None:
        resp = self.client.post(URL, _payload(), format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data.get("error_code"), "invalid_token")
        self.assertEqual(Order.objects.filter(channel_ref="ifood").count(), 0)

    def test_wrong_token_returns_403(self) -> None:
        resp = self.client.post(
            URL,
            _payload(),
            format="json",
            HTTP_X_IFOOD_WEBHOOK_TOKEN="nope",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data.get("error_code"), "invalid_token")
        self.assertEqual(Order.objects.filter(channel_ref="ifood").count(), 0)

    def test_wrong_token_via_query_returns_403(self) -> None:
        resp = self.client.post(
            URL + "?token=nope",
            _payload(),
            format="json",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(Order.objects.filter(channel_ref="ifood").count(), 0)

    @override_settings(SHOPMAN_IFOOD={"webhook_token": "", "merchant_id": ""})
    def test_unconfigured_token_rejects_everything(self) -> None:
        """Same code path in dev and prod — no token means no access, period."""
        resp = self.client.post(
            URL,
            _payload(),
            format="json",
            HTTP_X_IFOOD_WEBHOOK_TOKEN="anything",
        )
        self.assertEqual(resp.status_code, 403)


@override_settings(SHOPMAN_IFOOD=IFOOD_WEBHOOK_SETTINGS)
class IFoodWebhookValidationTests(TestCase):
    """Payload validation."""

    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        Channel.objects.get_or_create(
            ref="ifood", defaults={"name": "iFood", "is_active": True}
        )

    def _post(self, payload) -> object:
        return self.client.post(
            URL,
            payload,
            format="json",
            HTTP_X_IFOOD_WEBHOOK_TOKEN="test-ifood-token",
        )

    def test_missing_order_id_returns_400(self) -> None:
        payload = _payload()
        del payload["order_id"]
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data.get("error_code"), "missing_order_id")

    def test_empty_items_returns_400(self) -> None:
        payload = _payload()
        payload["items"] = []
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data.get("error_code"), "missing_items")

    def test_non_object_payload_returns_400(self) -> None:
        resp = self._post(["not", "a", "dict"])
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data.get("error_code"), "invalid_payload")


@override_settings(SHOPMAN_IFOOD=IFOOD_WEBHOOK_SETTINGS)
class IFoodWebhookIngestTests(TestCase):
    """Valid-token path: ingest + idempotency."""

    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        Channel.objects.get_or_create(
            ref="ifood", defaults={"name": "iFood", "is_active": True}
        )

    def _post(self, payload: dict) -> object:
        return self.client.post(
            URL,
            payload,
            format="json",
            HTTP_X_IFOOD_WEBHOOK_TOKEN="test-ifood-token",
        )

    def test_valid_token_creates_order(self) -> None:
        resp = self._post(_payload("IFOOD-NEW-42"))
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["status"], "accepted")
        order_ref = resp.data["order_ref"]

        order = Order.objects.get(ref=order_ref)
        self.assertEqual(order.channel_ref, "ifood")
        self.assertEqual(order.external_ref, "IFOOD-NEW-42")
        # total computed from items (2 × 750)
        self.assertEqual(order.total_q, 1500)

        replay = self._post(_payload("IFOOD-NEW-42"))
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(replay.data["order_ref"], order_ref)
        self.assertEqual(
            Order.objects.filter(channel_ref="ifood", external_ref="IFOOD-NEW-42").count(),
            1,
        )
        self.assertEqual(IdempotencyKey.objects.filter(scope="webhook:ifood").count(), 1)

    def test_replay_returns_already_processed_no_duplicate(self) -> None:
        # Simulate an already-ingested order directly, to keep this test
        # focused on the webhook's idempotency branch rather than on the
        # full ingest+dispatch pipeline (covered in its own tests).
        pre_existing = Order.objects.create(
            ref="ORD-IFOOD-REPLAY",
            channel_ref="ifood",
            external_ref="IFOOD-REPLAY-99",
            handle_type="ifood_order",
            handle_ref="IFOOD-REPLAY-99",
            status=Order.Status.NEW,
            total_q=1500,
            data={},
            snapshot={},
        )

        resp = self._post(_payload("IFOOD-REPLAY-99"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "already_processed")
        self.assertEqual(resp.data["order_ref"], pre_existing.ref)

        self.assertEqual(
            Order.objects.filter(
                channel_ref="ifood", external_ref="IFOOD-REPLAY-99"
            ).count(),
            1,
        )

    def test_in_progress_replay_returns_409(self) -> None:
        from shopman.shop.services.webhook_idempotency import stable_webhook_key

        IdempotencyKey.objects.create(
            scope="webhook:ifood",
            key=f"order:{stable_webhook_key('IFOOD-IN-PROGRESS')}",
            status="in_progress",
        )

        resp = self._post(_payload("IFOOD-IN-PROGRESS"))
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["status"], "in_progress")
        self.assertEqual(Order.objects.filter(channel_ref="ifood").count(), 0)

    def test_admin_simulation_entry_point_still_works(self) -> None:
        """Regression: the admin action's direct ingest path still works.

        The admin action calls :func:`ifood_ingest.ingest` with a locally
        built payload. That path must keep working — the webhook must not
        shadow or break it.
        """
        from shopman.shop.services import ifood_ingest

        payload = {
            "order_code": "IFOOD-ADMIN-TEST",
            "merchant_id": "mock-merchant",
            "customer": {"name": "Admin Sim", "phone": ""},
            "delivery": {"type": "DELIVERY", "address": "Rua Admin, 1"},
            "items": [{"sku": "PAO", "qty": 1, "unit_price_q": 500}],
        }
        order = ifood_ingest.ingest(payload)
        self.assertEqual(order.channel_ref, "ifood")
        self.assertEqual(order.external_ref, "IFOOD-ADMIN-TEST")


@override_settings(SHOPMAN_IFOOD=IFOOD_WEBHOOK_SETTINGS)
class IFoodWebhookIngestErrorTests(TestCase):
    """Non-retryable ingest errors surface as 400 (not 500)."""

    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        Channel.objects.get_or_create(
            ref="ifood", defaults={"name": "iFood", "is_active": True}
        )

    def test_ingest_error_returns_400(self) -> None:
        from shopman.shop.services.ifood_ingest import IFoodIngestError

        with patch(
            "shopman.shop.webhooks.ifood.ifood_ingest.ingest",
            side_effect=IFoodIngestError("item_missing_sku", "item #1 sem sku"),
        ):
            resp = self.client.post(
                URL,
                _payload("IFOOD-BAD-SKU"),
                format="json",
                HTTP_X_IFOOD_WEBHOOK_TOKEN="test-ifood-token",
            )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data.get("error_code"), "item_missing_sku")
