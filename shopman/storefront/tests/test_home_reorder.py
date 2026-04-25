"""Tests for HomeView._reorder_context (WP-O2 — reorder suggestion)."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, TestCase
from django.utils import timezone
from shopman.guestman.models import Customer, CustomerGroup
from shopman.orderman.models import Order

from shopman.storefront.views.home import REORDER_MIN_DAYS, HomeView

ITEMS = [
    {"line_id": "L1", "sku": "CROIS-01", "name": "Croissant Clássico", "qty": 2,
     "unit_price_q": 750, "line_total_q": 1500, "meta": {}},
    {"line_id": "L2", "sku": "PAO-001", "name": "Pão de Centeio", "qty": 1,
     "unit_price_q": 500, "line_total_q": 500, "meta": {}},
]


def _make_request(customer_uuid=None, customer_name=None):
    rf = RequestFactory()
    req = rf.get("/")
    if customer_uuid is not None:
        req.customer = SimpleNamespace(
            uuid=customer_uuid,
            name=customer_name or "Test Customer",
        )
    else:
        req.customer = None
    return req


class ReorderContextTests(TestCase):
    def setUp(self):
        group = CustomerGroup.objects.create(
            ref="regular", name="Regular", is_default=True, priority=0
        )
        self.customer = Customer.objects.create(
            ref="CUST-RO-001",
            first_name="João",
            last_name="Silva",
            phone="+5543999990001",
            group=group,
        )

    def _create_order(self, days_ago: int, items=None) -> Order:
        created = timezone.now() - timedelta(days=days_ago)
        order = Order.objects.create(
            ref=f"ORD-RO-{days_ago}d",
            channel_ref="web",
            session_key=f"sk-ro-{days_ago}d",
            status=Order.Status.COMPLETED,
            snapshot={"items": ITEMS if items is None else items, "pricing": {"total_q": 2000}},
            data={"customer_ref": self.customer.ref},
            total_q=2000,
        )
        # Override auto_now_add to simulate past creation
        Order.objects.filter(pk=order.pk).update(created_at=created)
        return order

    # ── No customer ─────────────────────────────────────────────────────

    def test_unauthenticated_returns_none(self):
        req = _make_request()  # no customer
        ref, items = HomeView._reorder_context(req)
        self.assertIsNone(ref)
        self.assertEqual(items, [])

    # ── Customer with no orders ──────────────────────────────────────────

    def test_no_orders_returns_none(self):
        req = _make_request(customer_uuid=self.customer.uuid)
        ref, items = HomeView._reorder_context(req)
        self.assertIsNone(ref)
        self.assertEqual(items, [])

    # ── days_since <= REORDER_MIN_DAYS ───────────────────────────────────

    def test_recent_order_returns_none(self):
        self._create_order(days_ago=REORDER_MIN_DAYS)  # exactly at threshold
        req = _make_request(customer_uuid=self.customer.uuid)
        ref, items = HomeView._reorder_context(req)
        self.assertIsNone(ref)
        self.assertEqual(items, [])

    def test_one_day_old_returns_none(self):
        self._create_order(days_ago=1)
        req = _make_request(customer_uuid=self.customer.uuid)
        ref, items = HomeView._reorder_context(req)
        self.assertIsNone(ref)
        self.assertEqual(items, [])

    # ── days_since > REORDER_MIN_DAYS ────────────────────────────────────

    def test_old_order_returns_ref_and_items(self):
        order = self._create_order(days_ago=REORDER_MIN_DAYS + 1)
        req = _make_request(customer_uuid=self.customer.uuid)
        ref, items = HomeView._reorder_context(req)
        self.assertEqual(ref, order.ref)
        self.assertEqual(len(items), len(ITEMS))
        self.assertEqual(items[0]["name"], "Croissant Clássico")
        self.assertEqual(items[0]["qty"], 2)

    def test_returns_most_recent_order(self):
        # Older order should NOT win
        self._create_order(days_ago=30)
        recent = self._create_order(days_ago=REORDER_MIN_DAYS + 1)
        # Give the recent one a distinct ref suffix
        Order.objects.filter(pk=recent.pk).update(ref="ORD-RO-RECENT")
        req = _make_request(customer_uuid=self.customer.uuid)
        ref, _ = HomeView._reorder_context(req)
        self.assertEqual(ref, "ORD-RO-RECENT")

    def test_order_with_empty_snapshot_items(self):
        self._create_order(days_ago=REORDER_MIN_DAYS + 1, items=[])
        req = _make_request(customer_uuid=self.customer.uuid)
        ref, items = HomeView._reorder_context(req)
        # ref still returned even with empty items
        self.assertIsNotNone(ref)
        self.assertEqual(items, [])

    # ── Orders from other customers are excluded ──────────────────────────

    def test_other_customer_orders_not_returned(self):
        # Order belongs to a different customer ref
        Order.objects.create(
            ref="ORD-RO-OTHER",
            channel_ref="web",
            session_key="sk-ro-other",
            status=Order.Status.COMPLETED,
            snapshot={"items": ITEMS, "pricing": {"total_q": 1500}},
            data={"customer_ref": "OTHER-CUST"},
            total_q=1500,
        )
        req = _make_request(customer_uuid=self.customer.uuid)
        ref, items = HomeView._reorder_context(req)
        self.assertIsNone(ref)
        self.assertEqual(items, [])

    # ── Exception safety ─────────────────────────────────────────────────

    def test_exception_in_customer_lookup_returns_none(self):
        req = _make_request(customer_uuid=self.customer.uuid)
        with patch(
            "shopman.guestman.services.customer.get_by_uuid",
            side_effect=Exception("db down"),
        ):
            ref, items = HomeView._reorder_context(req)
        self.assertIsNone(ref)
        self.assertEqual(items, [])
