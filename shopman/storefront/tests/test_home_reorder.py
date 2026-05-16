"""Tests for HomeView._reorder_context (WP-O2 — reorder suggestion)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, TestCase
from django.utils import timezone
from shopman.guestman.models import Customer, CustomerGroup
from shopman.offerman.models import Product
from shopman.orderman.models import Order, OrderItem

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

    # ── Recent orders ─────────────────────────────────────────────────────

    def test_recent_order_returns_ref_and_items(self):
        order = self._create_order(days_ago=0)
        req = _make_request(customer_uuid=self.customer.uuid)
        ref, items = HomeView._reorder_context(req)
        self.assertEqual(ref, order.ref)
        self.assertEqual(len(items), len(ITEMS))

    def test_one_day_old_returns_ref_and_items(self):
        order = self._create_order(days_ago=1)
        req = _make_request(customer_uuid=self.customer.uuid)
        ref, items = HomeView._reorder_context(req)
        self.assertEqual(ref, order.ref)
        self.assertEqual(len(items), len(ITEMS))

    # ── Prior orders, without an age gate ────────────────────────────────

    def test_old_order_returns_ref_and_items(self):
        order = self._create_order(days_ago=REORDER_MIN_DAYS + 1)
        req = _make_request(customer_uuid=self.customer.uuid)
        ref, items = HomeView._reorder_context(req)
        self.assertEqual(ref, order.ref)
        self.assertEqual(len(items), len(ITEMS))
        self.assertEqual(items[0]["name"], "Croissant Clássico")
        self.assertEqual(items[0]["qty"], 2)

    def test_home_renders_reorder_cta_when_customer_has_previous_order(self):
        self._create_order(days_ago=0)
        req = _make_request(customer_uuid=self.customer.uuid, customer_name=self.customer.first_name)

        response = HomeView.as_view()(req)

        content = response.content.decode()
        self.assertIn('id="quick-reorder-cta"', content)
        self.assertLess(content.index('id="home-carousel"'), content.index('id="quick-reorder-cta"'))
        self.assertIn("Quer repetir seu último pedido, João?", content)
        self.assertIn("Repetir pedido", content)
        self.assertIn("Pedir de novo", content)
        self.assertIn("Quer repetir seu<br>último pedido", content)

    def test_home_reorder_formats_snapshot_quantities_for_customer_display(self):
        self._create_order(
            days_ago=0,
            items=[
                {"sku": "FOC-001", "name": "Focaccia", "qty": "1.000", "unit_price_q": 1200},
                {"sku": "BAG-001", "name": "Baguete", "qty": "2.500", "unit_price_q": 900},
            ],
        )
        req = _make_request(customer_uuid=self.customer.uuid, customer_name=self.customer.first_name)

        response = HomeView.as_view()(req)

        content = response.content.decode()
        self.assertIn("1×</span>", content)
        self.assertIn(">Focaccia</span>", content)
        self.assertIn("2,5×</span>", content)
        self.assertIn(">Baguete</span>", content)
        self.assertNotIn("1.000×", content)
        self.assertNotIn("2.500×", content)
        self.assertNotIn("item do pedido", content)

    def test_home_reorder_uses_catalog_name_when_order_item_name_is_empty(self):
        Product.objects.create(sku="CAPPUCCINO", name="Cappuccino", base_price_q=1200)
        self._create_order(
            days_ago=0,
            items=[
                {"sku": "CAPPUCCINO", "name": "", "qty": "1.000", "unit_price_q": 1200},
            ],
        )
        req = _make_request(customer_uuid=self.customer.uuid, customer_name=self.customer.first_name)

        response = HomeView.as_view()(req)

        content = response.content.decode()
        self.assertIn("1×</span>", content)
        self.assertIn(">Cappuccino</span>", content)
        self.assertNotIn("item do pedido", content)

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
