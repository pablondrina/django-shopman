"""
Tests for PedidoMarkPaidView — WP-R4.

POST /pedidos/<ref>/mark-paid/ → marks dinheiro/counter orders as paid.
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase

from shopman.omniman.ids import generate_idempotency_key, generate_session_key
from shopman.omniman.models import Order, Session
from shopman.omniman.services.commit import CommitService
from shopman.omniman.services.modify import ModifyService
from shopman.models import Channel


def _create_order(channel_ref: str = "balcao", payment_method: str = "dinheiro") -> Order:
    session_key = generate_session_key()
    Session.objects.create(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
        pricing_policy="fixed",
        edit_policy="open",
        handle_type="pos",
        handle_ref="pos:test",
    )
    ModifyService.modify_session(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=[
            {"op": "add_line", "sku": "TEST-SKU", "qty": 1, "unit_price_q": 1500},
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
    return Order.objects.get(ref=result["order_ref"])


class MarkPaidTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.staff = User.objects.create_user("staff_user", password="pw", is_staff=True)
        self.regular = User.objects.create_user("regular_user", password="pw", is_staff=False)
        self.channel = Channel.objects.create(
            ref="balcao",
            name="Balcão",
            is_active=True,
        )
        self.client.force_login(self.staff)

    def test_mark_paid_happy_path(self) -> None:
        """POST mark-paid → marked_paid_by recorded (Payman is canonical status source)."""
        order = _create_order()
        resp = self.client.post(f"/pedidos/{order.ref}/mark-paid/")
        self.assertEqual(resp.status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.data.get("payment", {}).get("marked_paid_by"), "staff_user")
        # Status is NOT written to order.data — Payman is canonical
        self.assertNotIn("status", order.data.get("payment", {}))

    def test_mark_paid_transitions_new_to_confirmed(self) -> None:
        """mark-paid on a new order → transitions to confirmed."""
        order = _create_order()
        # Force back to "new" to test the transition (balcao may auto-confirm)
        Order.objects.filter(pk=order.pk).update(status="new")
        order.refresh_from_db()

        self.client.post(f"/pedidos/{order.ref}/mark-paid/")

        order.refresh_from_db()
        self.assertEqual(order.status, "confirmed")

    def test_mark_paid_idempotent(self) -> None:
        """mark-paid twice → no error, marked_paid_by unchanged."""
        order = _create_order()
        self.client.post(f"/pedidos/{order.ref}/mark-paid/")
        resp2 = self.client.post(f"/pedidos/{order.ref}/mark-paid/")

        self.assertEqual(resp2.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.data.get("payment", {}).get("marked_paid_by"), "staff_user")

    def test_mark_paid_staff_only(self) -> None:
        """Non-staff user → redirected to login."""
        order = _create_order()
        self.client.force_login(self.regular)
        resp = self.client.post(f"/pedidos/{order.ref}/mark-paid/")

        # Redirected to admin login
        self.assertIn(resp.status_code, [302, 403])

    def test_mark_paid_records_operator(self) -> None:
        """mark-paid stores operator username."""
        order = _create_order()
        self.client.post(f"/pedidos/{order.ref}/mark-paid/")

        order.refresh_from_db()
        self.assertEqual(
            order.data.get("payment", {}).get("marked_paid_by"),
            "staff_user",
        )

    def test_mark_paid_does_not_double_transition(self) -> None:
        """mark-paid on already-confirmed order doesn't crash."""
        order = _create_order()
        order.transition_status("confirmed", actor="test")

        resp = self.client.post(f"/pedidos/{order.ref}/mark-paid/")
        self.assertEqual(resp.status_code, 200)

        order.refresh_from_db()
        # Operator marker is set
        self.assertEqual(order.data.get("payment", {}).get("marked_paid_by"), "staff_user")
        # Status unchanged (already confirmed)
        self.assertEqual(order.status, "confirmed")
