"""
Tests for api/polling module (order polling endpoint).
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory

from shopman.omniman.api.polling import order_stream_view
from shopman.omniman.models import Channel, Order

User = get_user_model()


class OrderStreamViewTests(TestCase):
    """Tests for order_stream_view polling endpoint."""

    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.channel = Channel.objects.create(
            ref="sse-test",
            name="SSE Test Channel",
        )
        # Create staff user for authentication
        self.staff_user = User.objects.create_user(
            username="staff_sse",
            password="testpass",
            is_staff=True,
        )

    def _create_order(self, ref, **kwargs):
        """Helper to create an Order (items are related model, not field)."""
        defaults = {
            "channel": self.channel,
            "status": "new",
            "total_q": 0,  # Required field
        }
        defaults.update(kwargs)
        return Order.objects.create(ref=ref, **defaults)

    def _get_response(self, since=None):
        """Helper to make authenticated request."""
        url = "/admin/ordering/order/stream/"
        if since is not None:
            url += f"?since={since}"
        request = self.factory.get(url)
        request.user = self.staff_user
        return order_stream_view(request)

    def test_returns_last_id_without_since_param(self) -> None:
        """Should return last order ID when no 'since' param."""
        # Create some orders
        self._create_order("ORD-SSE-001")
        order2 = self._create_order("ORD-SSE-002")

        response = self._get_response()

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["orders"], [])
        self.assertEqual(data["last_id"], order2.id)

    def test_returns_zero_last_id_when_no_orders(self) -> None:
        """Should return last_id=0 when no orders exist."""
        response = self._get_response()

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["orders"], [])
        self.assertEqual(data["last_id"], 0)

    def test_returns_orders_since_id(self) -> None:
        """Should return orders with ID greater than 'since'."""
        order1 = self._create_order("ORD-SSE-010")
        order2 = self._create_order(
            "ORD-SSE-011",
            status="confirmed",
            total_q=2500,
            handle_ref="TABLE-5",
        )

        response = self._get_response(since=order1.id)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(len(data["orders"]), 1)
        self.assertEqual(data["orders"][0]["ref"], "ORD-SSE-011")
        self.assertEqual(data["orders"][0]["status"], "confirmed")
        self.assertEqual(data["orders"][0]["channel"], "SSE Test Channel")
        self.assertEqual(data["orders"][0]["total"], "25.0")
        self.assertEqual(data["orders"][0]["handle_ref"], "TABLE-5")
        self.assertEqual(data["last_id"], order2.id)

    def test_returns_empty_when_no_new_orders(self) -> None:
        """Should return empty list when no orders since ID."""
        order = self._create_order("ORD-SSE-020")

        response = self._get_response(since=order.id)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["orders"], [])
        self.assertEqual(data["last_id"], order.id)

    def test_returns_error_for_invalid_since_param(self) -> None:
        """Should return 400 for non-numeric 'since' param."""
        response = self._get_response(since="invalid")

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertIn("error", data)
        self.assertIn("Invalid", data["error"])

    def test_limits_to_10_orders(self) -> None:
        """Should limit response to 10 orders."""
        # Create 15 orders
        for i in range(15):
            self._create_order(f"ORD-SSE-BATCH-{i:03d}")

        # Get orders since ID 0
        response = self._get_response(since=0)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(len(data["orders"]), 10)

    def test_handles_order_with_zero_total(self) -> None:
        """Should handle orders with zero total_q."""
        order = self._create_order("ORD-SSE-ZEROTOTAL", total_q=0)

        response = self._get_response(since=order.id - 1)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["orders"][0]["total"], "0")

    def test_returns_orders_in_order(self) -> None:
        """Should return orders sorted by ID ascending."""
        self._create_order("ORD-A")
        self._create_order("ORD-B")
        self._create_order("ORD-C")

        response = self._get_response(since=0)

        data = json.loads(response.content)
        refs = [o["ref"] for o in data["orders"]]
        self.assertEqual(refs, ["ORD-A", "ORD-B", "ORD-C"])
