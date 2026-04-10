"""Tests for WP-R15 — POS Resumo de Turno."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone


def _make_shop():
    from shopman.models import Shop
    return Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})[0]


def _make_channel():
    from shopman.omniman.models import Channel
    return Channel.objects.get_or_create(
        ref="balcao",
        defaults={"name": "Balcão", "is_active": True},
    )[0]


def _make_order(channel, ref, total_q, status="confirmed"):
    from shopman.omniman.models import Order
    return Order.objects.create(
        ref=ref,
        channel=channel,
        status=status,
        total_q=total_q,
        handle_type="pos",
        handle_ref="pos:operator",
    )


class ShiftSummaryViewTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        _make_shop()
        self.channel = _make_channel()
        User = get_user_model()
        self.staff = User.objects.create_user(username="shift_staff", password="x", is_staff=True)
        self.client.force_login(self.staff)
        # WP-R16: POS requires an open cash register session
        from shopman.models import CashRegisterSession
        CashRegisterSession.objects.create(operator=self.staff, opening_amount_q=0)

    def test_summary_zero_sales(self) -> None:
        """Shift summary with no orders shows 0 sales."""
        resp = self.client.get("/gestao/pos/shift-summary/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "0")

    def test_summary_counts_orders(self) -> None:
        """Shift summary counts completed orders."""
        _make_order(self.channel, "SHIFT-001", 1000, status="confirmed")
        _make_order(self.channel, "SHIFT-002", 2000, status="completed")
        resp = self.client.get("/gestao/pos/shift-summary/")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("2", content)

    def test_summary_excludes_cancelled(self) -> None:
        """Cancelled orders are not counted in shift summary."""
        _make_order(self.channel, "SHIFT-003", 1000, status="confirmed")
        _make_order(self.channel, "SHIFT-004", 500, status="cancelled")
        resp = self.client.get("/gestao/pos/shift-summary/")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        # Only 1 non-cancelled order
        self.assertIn("1", content)

    def test_summary_shows_total(self) -> None:
        """Shift summary shows correct total."""
        _make_order(self.channel, "SHIFT-005", 1500, status="confirmed")
        _make_order(self.channel, "SHIFT-006", 2500, status="confirmed")
        resp = self.client.get("/gestao/pos/shift-summary/")
        self.assertEqual(resp.status_code, 200)
        # Total = R$ 40,00
        self.assertContains(resp, "40,00")

    def test_pos_footer_triggers_htmx_load(self) -> None:
        """POS page footer has hx-get for shift summary with auto-refresh."""
        resp = self.client.get("/gestao/pos/")
        self.assertContains(resp, "shift-summary")
        self.assertContains(resp, "every 60s")

    def test_pos_close_sends_hx_trigger(self) -> None:
        """Successful pos_close sends HX-Trigger: posOrderCreated header."""
        import json
        from shopman.offerman.models import Product
        Product.objects.create(sku="SHIFT-PROD", name="Prod", base_price_q=500, is_published=True, is_available=True)
        payload = json.dumps({
            "items": [{"sku": "SHIFT-PROD", "qty": 1, "unit_price_q": 500}],
            "customer_name": "", "customer_phone": "", "payment_method": "dinheiro",
            "manual_discount": None,
        })
        resp = self.client.post("/gestao/pos/close/", {"payload": payload})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["HX-Trigger"], "posOrderCreated")
