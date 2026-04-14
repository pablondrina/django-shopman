"""
Tests for Manychat Webhook (inbound).

Testa o fluxo: Manychat → POST /webhook/manychat/ → Shopman services.

SKIP: Manychat webhook moved out during WP-H0d cleanup.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Manychat webhook moved — pending reimplementation in channels/")


from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from shopman.orderman.models import Order, Session

from shopman.shop.models import Channel

WEBHOOK_SETTINGS = {
    "AUTH_TOKEN": "test-secret-token",
    "DEFAULT_CHANNEL": "whatsapp",
    "AUTH_HEADER": "X-Webhook-Token",
}


@override_settings(SHOPMAN_WEBHOOK=WEBHOOK_SETTINGS)
class ManychatWebhookTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        self.channel = Channel.objects.create(
            ref="whatsapp",
            name="WhatsApp",
            is_active=True,
        )
        self.url = "/webhook/manychat/"
        self.auth_header = {"HTTP_X_WEBHOOK_TOKEN": "test-secret-token"}

    def _post(self, payload: dict, **extra) -> object:
        headers = {**self.auth_header, **extra}
        return self.client.post(self.url, payload, format="json", **headers)

    # ── new_order ─────────────────────────────────────────────

    def test_new_order_via_webhook(self) -> None:
        """POST new_order → Session criada com items."""
        resp = self._post({
            "action": "new_order",
            "subscriber_id": "12345",
            "data": {
                "customer_phone": "+5543999999999",
                "customer_name": "Maria",
                "items": [
                    {"sku": "PAO-FERMENT", "qty": 2, "unit_price_q": 1200},
                    {"sku": "CROISSANT", "qty": 3, "unit_price_q": 850},
                ],
            },
        })
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertIn("session_key", str(resp.data))

        # Verify session was created
        session = Session.objects.get(
            channel_ref=self.channel.ref,
            handle_type="subscriber",
            handle_ref="12345",
        )
        self.assertEqual(session.state, "open")
        self.assertEqual(len(session.items), 2)

    def test_new_order_reuses_open_session(self) -> None:
        """Se subscriber já tem session open, reutiliza."""
        # First order
        self._post({
            "action": "new_order",
            "subscriber_id": "12345",
            "data": {
                "items": [{"sku": "PAO-FERMENT", "qty": 1, "unit_price_q": 1200}],
            },
        })
        # Second order — should reuse session
        self._post({
            "action": "new_order",
            "subscriber_id": "12345",
            "data": {
                "items": [{"sku": "CROISSANT", "qty": 1, "unit_price_q": 850}],
            },
        })

        sessions = Session.objects.filter(
            channel_ref=self.channel.ref,
            handle_type="subscriber",
            handle_ref="12345",
            state="open",
        )
        self.assertEqual(sessions.count(), 1)
        session = sessions.first()
        # Should have items from both requests
        self.assertEqual(len(session.items), 2)

    # ── add_item ──────────────────────────────────────────────

    def test_add_item_via_webhook(self) -> None:
        """Adiciona item a session existente."""
        # Create session first
        resp1 = self._post({
            "action": "new_order",
            "subscriber_id": "12345",
            "data": {
                "items": [{"sku": "PAO-FERMENT", "qty": 1, "unit_price_q": 1200}],
            },
        })
        session_key = None
        for fv in resp1.data.get("set_field_values", []):
            if fv["field_name"] == "session_key":
                session_key = fv["field_value"]
        self.assertIsNotNone(session_key)

        # Add item
        resp2 = self._post({
            "action": "add_item",
            "subscriber_id": "12345",
            "data": {
                "session_key": session_key,
                "sku": "CROISSANT",
                "qty": 3,
                "unit_price_q": 850,
            },
        })
        self.assertEqual(resp2.status_code, 200, resp2.data)

        session = Session.objects.get(session_key=session_key)
        self.assertEqual(len(session.items), 2)

    # ── commit_order ──────────────────────────────────────────

    def test_commit_via_webhook(self) -> None:
        """Commit → Order criada."""
        # Create session with item
        resp1 = self._post({
            "action": "new_order",
            "subscriber_id": "99999",
            "data": {
                "items": [{"sku": "BAGUETE", "qty": 1, "unit_price_q": 1500}],
            },
        })
        session_key = None
        for fv in resp1.data.get("set_field_values", []):
            if fv["field_name"] == "session_key":
                session_key = fv["field_value"]

        # Commit
        resp2 = self._post({
            "action": "commit_order",
            "subscriber_id": "99999",
            "data": {"session_key": session_key},
        })
        self.assertEqual(resp2.status_code, 200, resp2.data)

        # Verify order exists
        order_ref = None
        for fv in resp2.data.get("set_field_values", []):
            if fv["field_name"] == "order_ref":
                order_ref = fv["field_value"]
        self.assertIsNotNone(order_ref)

        order = Order.objects.get(ref=order_ref)
        self.assertIn(order.status, ("new", "confirmed"))
        self.assertEqual(order.total_q, 1500)

    # ── check_status ──────────────────────────────────────────

    def test_check_status_via_webhook(self) -> None:
        """Consulta status retorna corretamente."""
        # Create order via session → commit
        resp1 = self._post({
            "action": "new_order",
            "subscriber_id": "77777",
            "data": {
                "items": [{"sku": "PAIN-CHOC", "qty": 2, "unit_price_q": 950}],
            },
        })
        session_key = None
        for fv in resp1.data.get("set_field_values", []):
            if fv["field_name"] == "session_key":
                session_key = fv["field_value"]

        resp2 = self._post({
            "action": "commit_order",
            "subscriber_id": "77777",
            "data": {"session_key": session_key},
        })
        order_ref = None
        for fv in resp2.data.get("set_field_values", []):
            if fv["field_name"] == "order_ref":
                order_ref = fv["field_value"]

        # Check status
        resp3 = self._post({
            "action": "check_status",
            "subscriber_id": "77777",
            "data": {"order_ref": order_ref},
        })
        self.assertEqual(resp3.status_code, 200, resp3.data)

        # Verify order_status in fields
        status_field = None
        for fv in resp3.data.get("set_field_values", []):
            if fv["field_name"] == "order_status":
                status_field = fv["field_value"]
        self.assertIn(status_field, ("new", "confirmed"))

    # ── list_menu ─────────────────────────────────────────────

    def test_list_menu_via_webhook(self) -> None:
        """list_menu retorna mensagem (catalog backend indisponível = fallback)."""
        resp = self._post({
            "action": "list_menu",
            "subscriber_id": "12345",
            "data": {},
        })
        self.assertEqual(resp.status_code, 200, resp.data)
        # Without catalog backend, returns fallback message
        self.assertIn("indisponível", resp.data["content"]["messages"][0]["text"])

    # ── Auth ──────────────────────────────────────────────────

    def test_invalid_auth_token(self) -> None:
        """Request com token errado → 403."""
        resp = self.client.post(
            self.url,
            {"action": "list_menu", "subscriber_id": "123"},
            format="json",
            HTTP_X_WEBHOOK_TOKEN="wrong-token",
        )
        self.assertEqual(resp.status_code, 403)

    def test_missing_auth_token(self) -> None:
        """Request sem token → 403."""
        resp = self.client.post(
            self.url,
            {"action": "list_menu", "subscriber_id": "123"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    # ── Validation ────────────────────────────────────────────

    def test_unknown_action(self) -> None:
        """Action desconhecida → 400."""
        resp = self._post({
            "action": "do_magic",
            "subscriber_id": "12345",
        })
        self.assertEqual(resp.status_code, 400)

    def test_missing_subscriber_id(self) -> None:
        """subscriber_id ausente → 400."""
        resp = self._post({
            "action": "new_order",
        })
        self.assertEqual(resp.status_code, 400)
