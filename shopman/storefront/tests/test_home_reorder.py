"""Tests for the home reorder suggestion (presentation.home._reorder_context).

The reorder-suggestion context (last order ref + items) feeds the API home
projection the Nuxt store consumes. The HTML rendering moved to the store; here
we cover the data logic via the kept presentation helper, which delegates to
``storefront.services.orders.last_reorder_context``.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, TestCase
from django.utils import timezone
from shopman.guestman.models import Customer, CustomerGroup
from shopman.orderman.models import Order, OrderItem

from shopman.storefront.presentation.home import _reorder_context

# A "sufficiently old" offset; the suggestion has no age gate (min_days=0).
OLD_DAYS = 30

ITEMS = [
    {"line_id": "L1", "sku": "CROIS-01", "name": "Croissant Clássico", "qty": 2,
     "unit_price_q": 750, "line_total_q": 1500, "meta": {}},
    {"line_id": "L2", "sku": "PAO-001", "name": "Pão de Centeio", "qty": 1,
     "unit_price_q": 500, "line_total_q": 500, "meta": {}},
]


def _make_request(customer_uuid=None, customer_name=None):
    rf = RequestFactory()
    req = rf.get("/")
    req.session = {}
    if customer_uuid is not None:
        req.customer = SimpleNamespace(
            uuid=customer_uuid,
            name=customer_name or "Test Customer",
            phone="+5543999990001",
            email="",
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
        raw_items = ITEMS if items is None else items
        order = Order.objects.create(
            ref=f"ORD-RO-{days_ago}d",
            channel_ref="web",
            session_key=f"sk-ro-{days_ago}d",
            status=Order.Status.COMPLETED,
            snapshot={"items": raw_items, "pricing": {"total_q": 2000}},
            data={"customer_ref": self.customer.ref},
            total_q=2000,
        )
        for idx, item in enumerate(raw_items, start=1):
            qty = Decimal(str(item.get("qty", 1)))
            unit_price_q = int(item.get("unit_price_q", 0))
            line_total_q = int(item.get("line_total_q") or unit_price_q * int(qty))
            OrderItem.objects.create(
                order=order,
                line_id=item.get("line_id") or f"L{idx}",
                sku=item.get("sku") or f"SKU-{idx}",
                name=item.get("name", ""),
                qty=qty,
                unit_price_q=unit_price_q,
                line_total_q=line_total_q,
                meta=item.get("meta", {}),
            )
        # Override auto_now_add to simulate past creation
        Order.objects.filter(pk=order.pk).update(created_at=created)
        return order

    # ── No customer ─────────────────────────────────────────────────────

    def test_unauthenticated_returns_none(self):
        ref, items = _reorder_context(_make_request())  # no customer
        self.assertIsNone(ref)
        self.assertFalse(items)

    # ── Customer with no orders ──────────────────────────────────────────

    def test_no_orders_returns_none(self):
        ref, items = _reorder_context(_make_request(customer_uuid=self.customer.uuid))
        self.assertIsNone(ref)
        self.assertFalse(items)

    # ── Prior orders, without an age gate ────────────────────────────────

    def test_recent_order_returns_ref_and_items(self):
        order = self._create_order(days_ago=0)
        ref, items = _reorder_context(_make_request(customer_uuid=self.customer.uuid))
        self.assertEqual(ref, order.ref)
        self.assertEqual(len(items), len(ITEMS))

    def test_one_day_old_returns_ref_and_items(self):
        order = self._create_order(days_ago=1)
        ref, items = _reorder_context(_make_request(customer_uuid=self.customer.uuid))
        self.assertEqual(ref, order.ref)
        self.assertEqual(len(items), len(ITEMS))

    def test_old_order_returns_ref_and_items(self):
        order = self._create_order(days_ago=OLD_DAYS + 1)
        ref, items = _reorder_context(_make_request(customer_uuid=self.customer.uuid))
        self.assertEqual(ref, order.ref)
        self.assertEqual(len(items), len(ITEMS))
        self.assertEqual(items[0].name, "Croissant Clássico")
        self.assertEqual(items[0].qty, 2)

    def test_returns_most_recent_order(self):
        # Older order should NOT win
        self._create_order(days_ago=OLD_DAYS)
        recent = self._create_order(days_ago=1)
        Order.objects.filter(pk=recent.pk).update(ref="ORD-RO-RECENT")
        ref, _ = _reorder_context(_make_request(customer_uuid=self.customer.uuid))
        self.assertEqual(ref, "ORD-RO-RECENT")

    def test_order_with_empty_snapshot_items(self):
        self._create_order(days_ago=OLD_DAYS + 1, items=[])
        ref, items = _reorder_context(_make_request(customer_uuid=self.customer.uuid))
        # ref still returned even with empty items
        self.assertIsNotNone(ref)
        self.assertFalse(items)

    # ── Orders from other customers are excluded ──────────────────────────

    def test_other_customer_orders_not_returned(self):
        Order.objects.create(
            ref="ORD-RO-OTHER",
            channel_ref="web",
            session_key="sk-ro-other",
            status=Order.Status.COMPLETED,
            snapshot={"items": ITEMS, "pricing": {"total_q": 1500}},
            data={"customer_ref": "OTHER-CUST"},
            total_q=1500,
        )
        ref, items = _reorder_context(_make_request(customer_uuid=self.customer.uuid))
        self.assertIsNone(ref)
        self.assertFalse(items)

    # ── Exception safety ─────────────────────────────────────────────────

    def test_exception_in_reorder_lookup_returns_none(self):
        with patch(
            "shopman.storefront.services.orders.last_reorder_context",
            side_effect=Exception("db down"),
        ):
            ref, items = _reorder_context(_make_request(customer_uuid=self.customer.uuid))
        self.assertIsNone(ref)
        self.assertFalse(items)
