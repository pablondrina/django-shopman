"""Admin/Unfold integration guardrails for operational Backstage surfaces."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from django.contrib import admin
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from shopman.backstage.admin import navigation
from shopman.backstage.projections.dashboard import build_dashboard
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
from shopman.orderman.admin import OrderAdmin
from shopman.orderman.models import Order, OrderItem


class AdminNavigationTests(TestCase):
    def test_sidebar_prioritizes_live_operation_and_backoffice_tools(self) -> None:
        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser("admin", "admin@example.com", "pw")

        groups = admin.site.get_sidebar_list(request)
        titles = [group["title"] for group in groups]

        self.assertEqual(titles[0], "Operação ao vivo")
        self.assertIn("Pedidos e canais", titles)
        self.assertIn("Produção", titles)
        self.assertIn("Auditoria e acesso", titles)
        self.assertNotIn("Regras", titles)

        live_items = [item["title"] for item in groups[0]["items"] if item["has_permission"]]
        self.assertEqual(live_items[:3], ["Pedidos", "Produção", "Fechamento"])

    def test_sidebar_badges_count_operational_attention(self) -> None:
        Order.objects.create(
            ref="NAV-NEW",
            channel_ref="web",
            session_key="nav-session",
            status=Order.Status.NEW,
            total_q=1000,
            data={"payment": {"method": "cash"}},
        )

        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser("admin2", "admin2@example.com", "pw")

        self.assertEqual(navigation.badge_new_orders(request), "1")


class AdminDashboardSemanticsTests(TestCase):
    def test_production_kpi_uses_product_quantities_not_only_work_order_counts(self) -> None:
        recipe = Recipe.objects.create(
            ref="admin-ciabatta",
            name="Ciabatta",
            output_sku="CIABATTA",
            batch_size=10,
        )
        planned = craft.plan(recipe, 13, date=date.today())
        started = craft.plan(recipe, 8, date=date.today(), operator_ref="user:ana")
        craft.start(started, quantity=8, actor="test")
        finished = craft.plan(recipe, 5, date=date.today(), operator_ref="user:bia")
        craft.start(finished, quantity=5, actor="test")
        craft.finish(finished, finished=4, actor="test")

        production = build_dashboard().production

        self.assertEqual(production.open, 2)
        self.assertEqual(production.done, 1)
        self.assertEqual(production.planned_qty, "26")
        self.assertEqual(production.started_qty, "13")
        self.assertEqual(production.finished_qty, "4")
        self.assertEqual(production.loss_qty, "1")
        self.assertIn(planned.ref, [row.ref for row in production.wos])


class OrderAdminSemanticsTests(TestCase):
    def test_order_admin_distinguishes_lines_from_units(self) -> None:
        order = Order.objects.create(
            ref="ADM-ORDER",
            channel_ref="web",
            session_key="adm-order-session",
            status=Order.Status.CONFIRMED,
            total_q=3000,
            data={"payment": {"method": "cash"}},
        )
        OrderItem.objects.create(
            order=order,
            line_id="1",
            sku="CIABATTA",
            name="Ciabatta",
            qty=3,
            unit_price_q=1000,
            line_total_q=3000,
        )
        OrderItem.objects.create(
            order=order,
            line_id="2",
            sku="BAGUETTE",
            name="Baguette",
            qty=10,
            unit_price_q=0,
            line_total_q=0,
        )

        model_admin = OrderAdmin(Order, admin.site)

        self.assertEqual(model_admin.items_count_display(order), "2")
        self.assertEqual(model_admin.units_count_display(order), "13")


def test_legacy_admin_operational_templates_removed():
    root = Path(__file__).resolve().parents[3]

    assert not (root / "shopman/shop/templates/admin/shop/production.html").exists()
    assert not (root / "shopman/shop/templates/admin/shop/closing.html").exists()
