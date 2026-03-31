"""Tests for DayClosing model, closing view, cleanup_d1 command, and dashboard D-1 widget."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from django.db import IntegrityError
from django.test import Client, TestCase
from shopman.offering.models import Product
from shopman.stocking.models import Move, Quant
from shopman.stocking.models.position import Position
from shopman.stocking.services.movements import StockMovements

from shop.dashboard import _build_d1_table, _d1_stock
from shop.models import DayClosing, Shop

CLOSING_URL = "/admin/shop/shop/closing/"


class ProductMetadataTests(TestCase):
    def test_product_metadata_default_empty_dict(self):
        p = Product.objects.create(sku="TEST-META", name="Test", base_price_q=100)
        self.assertEqual(p.metadata, {})

    def test_product_metadata_allows_next_day_sale_queryable(self):
        p1 = Product.objects.create(sku="D1-YES", name="D1 Yes", base_price_q=100)
        p1.metadata["allows_next_day_sale"] = True
        p1.save(update_fields=["metadata"])

        p2 = Product.objects.create(sku="D1-NO", name="D1 No", base_price_q=100)

        d1_products = Product.objects.filter(metadata__allows_next_day_sale=True)
        self.assertIn(p1, d1_products)
        self.assertNotIn(p2, d1_products)


class DayClosingModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("operator", password="test")

    def test_day_closing_one_per_day_constraint(self):
        DayClosing.objects.create(date=date(2026, 3, 27), closed_by=self.user)
        with self.assertRaises(IntegrityError):
            DayClosing.objects.create(date=date(2026, 3, 27), closed_by=self.user)

    def test_day_closing_data_snapshot_format(self):
        snapshot = [
            {"sku": "PAO-FRANCES", "qty_remaining": 5, "qty_d1": 3, "qty_loss": 2},
            {"sku": "BAGUETE", "qty_remaining": 0, "qty_d1": 0, "qty_loss": 4},
        ]
        closing = DayClosing.objects.create(
            date=date(2026, 3, 26),
            closed_by=self.user,
            data=snapshot,
        )
        closing.refresh_from_db()
        self.assertEqual(len(closing.data), 2)
        self.assertEqual(closing.data[0]["sku"], "PAO-FRANCES")
        self.assertEqual(closing.data[0]["qty_d1"], 3)

    def test_day_closing_str(self):
        closing = DayClosing.objects.create(date=date(2026, 3, 25), closed_by=self.user)
        self.assertEqual(str(closing), "Fechamento 2026-03-25")

    def test_day_closing_default_data_empty_list(self):
        closing = DayClosing.objects.create(date=date(2026, 3, 24), closed_by=self.user)
        self.assertEqual(closing.data, [])


class ClosingViewTestBase(TestCase):
    """Shared setup for closing view tests."""

    @classmethod
    def setUpTestData(cls):
        cls.shop = Shop.objects.create(name="Test Shop")
        cls.admin_user = User.objects.create_superuser("admin", "admin@test.com", "admin123")
        cls.regular_user = User.objects.create_user("regular", password="test")

        # Give regular_user the closing permission
        perm = Permission.objects.get(codename="add_dayclosing")
        cls.operator_user = User.objects.create_user("operator", password="test")
        cls.operator_user.user_permissions.add(perm)

        # Positions
        cls.vitrine = Position.objects.create(
            ref="vitrine", name="Vitrine", kind="physical",
            is_saleable=True, is_default=True,
        )
        cls.ontem_pos = Position.objects.create(
            ref="ontem", name="Ontem (D-1)", kind="logical",
            is_saleable=True,
        )

        # Products
        cls.pao = Product.objects.create(
            sku="PAO-FRANCES", name="Pão Francês",
            base_price_q=150, shelf_life_days=0,
        )
        cls.pao.metadata["allows_next_day_sale"] = True
        cls.pao.save(update_fields=["metadata"])

        cls.baguete = Product.objects.create(
            sku="BAGUETE", name="Baguete",
            base_price_q=500, shelf_life_days=0,
        )
        # baguete: shelf_life_days=0 and no allows_next_day_sale → loss

        cls.conserva = Product.objects.create(
            sku="CONSERVA", name="Conserva Artesanal",
            base_price_q=2500, shelf_life_days=180,
        )
        # conserva: shelf_life_days > 0 → neutral


class ClosingPagePermissionTest(ClosingViewTestBase):
    def test_closing_page_requires_permission(self):
        client = Client()
        client.force_login(self.regular_user)
        resp = client.get(CLOSING_URL)
        self.assertEqual(resp.status_code, 302)


class ClosingPageListTest(ClosingViewTestBase):
    def test_closing_page_lists_skus_with_stock(self):
        StockMovements.receive(Decimal("10"), "PAO-FRANCES", position=self.vitrine, reason="produção")
        StockMovements.receive(Decimal("5"), "BAGUETE", position=self.vitrine, reason="produção")
        StockMovements.receive(Decimal("3"), "CONSERVA", position=self.vitrine, reason="produção")

        client = Client()
        client.force_login(self.admin_user)
        resp = client.get(CLOSING_URL)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("PAO-FRANCES", content)
        self.assertIn("BAGUETE", content)
        self.assertIn("CONSERVA", content)
        self.assertIn("D-1", content)  # badge for pao
        self.assertIn("Perda", content)  # badge for baguete
        self.assertIn("Neutro", content)  # badge for conserva


class ClosingMovesD1Test(ClosingViewTestBase):
    def test_closing_moves_d1_eligible_to_ontem(self):
        StockMovements.receive(Decimal("10"), "PAO-FRANCES", position=self.vitrine, reason="produção")

        client = Client()
        client.force_login(self.admin_user)
        resp = client.post(CLOSING_URL, {"qty_PAO-FRANCES": "7"})
        self.assertEqual(resp.status_code, 302)

        # Check: 7 moved to "ontem", 3 remaining in vitrine
        ontem_qty = Quant.objects.filter(
            sku="PAO-FRANCES", position=self.ontem_pos
        ).first()
        self.assertIsNotNone(ontem_qty)
        self.assertEqual(ontem_qty._quantity, Decimal("7"))

        vitrine_qty = Quant.objects.get(sku="PAO-FRANCES", position=self.vitrine)
        self.assertEqual(vitrine_qty._quantity, Decimal("3"))


class ClosingLossTest(ClosingViewTestBase):
    def test_closing_registers_loss_for_ineligible(self):
        StockMovements.receive(Decimal("5"), "BAGUETE", position=self.vitrine, reason="produção")

        client = Client()
        client.force_login(self.admin_user)
        resp = client.post(CLOSING_URL, {"qty_BAGUETE": "3"})
        self.assertEqual(resp.status_code, 302)

        vitrine_qty = Quant.objects.get(sku="BAGUETE", position=self.vitrine)
        self.assertEqual(vitrine_qty._quantity, Decimal("2"))

        # No stock in "ontem" for baguete
        ontem_qty = Quant.objects.filter(sku="BAGUETE", position=self.ontem_pos).first()
        self.assertTrue(ontem_qty is None or ontem_qty._quantity == 0)


class ClosingNeutralTest(ClosingViewTestBase):
    def test_closing_skips_non_perishable(self):
        StockMovements.receive(Decimal("3"), "CONSERVA", position=self.vitrine, reason="produção")

        client = Client()
        client.force_login(self.admin_user)
        # No qty_ field sent for neutral items
        resp = client.post(CLOSING_URL, {})
        self.assertEqual(resp.status_code, 302)

        # Conserva untouched
        vitrine_qty = Quant.objects.get(sku="CONSERVA", position=self.vitrine)
        self.assertEqual(vitrine_qty._quantity, Decimal("3"))


class ClosingRecordTest(ClosingViewTestBase):
    def test_closing_creates_day_closing_record(self):
        StockMovements.receive(Decimal("10"), "PAO-FRANCES", position=self.vitrine, reason="produção")

        client = Client()
        client.force_login(self.admin_user)
        client.post(CLOSING_URL, {"qty_PAO-FRANCES": "5"})

        closing = DayClosing.objects.filter(date=date.today()).first()
        self.assertIsNotNone(closing)
        self.assertEqual(closing.closed_by, self.admin_user)
        self.assertTrue(len(closing.data) > 0)

        pao_entry = next(d for d in closing.data if d["sku"] == "PAO-FRANCES")
        self.assertEqual(pao_entry["qty_d1"], 5)


class ClosingDuplicateTest(ClosingViewTestBase):
    def test_closing_blocks_duplicate_same_day(self):
        StockMovements.receive(Decimal("10"), "PAO-FRANCES", position=self.vitrine, reason="produção")

        client = Client()
        client.force_login(self.admin_user)
        # First closing
        client.post(CLOSING_URL, {"qty_PAO-FRANCES": "5"})
        self.assertEqual(DayClosing.objects.filter(date=date.today()).count(), 1)

        # Second attempt
        resp = client.post(CLOSING_URL, {"qty_PAO-FRANCES": "3"})
        self.assertEqual(resp.status_code, 302)
        # Still only one closing
        self.assertEqual(DayClosing.objects.filter(date=date.today()).count(), 1)


class ClosingAlertOldD1Test(ClosingViewTestBase):
    def test_closing_shows_alert_for_old_d1(self):
        # Create old D-1 stock
        StockMovements.receive(Decimal("5"), "PAO-FRANCES", position=self.ontem_pos, reason="d1:2026-03-01")

        # Backdate the move to > 1 day ago
        move = Move.objects.filter(reason="d1:2026-03-01").first()
        Move.objects.filter(pk=move.pk).update(
            timestamp=move.timestamp - timedelta(days=3)
        )

        client = Client()
        client.force_login(self.admin_user)
        resp = client.get(CLOSING_URL)
        content = resp.content.decode()
        self.assertIn("D-1 com mais de 1 dia", content)


class CleanupD1CommandTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ontem_pos = Position.objects.create(
            ref="ontem", name="Ontem (D-1)", kind="logical",
            is_saleable=True,
        )
        Product.objects.create(sku="PAO-FRANCES", name="Pão Francês", base_price_q=150)

    def test_cleanup_d1_removes_old_stock(self):
        StockMovements.receive(Decimal("5"), "PAO-FRANCES", position=self.ontem_pos, reason="d1:2026-03-20")

        # Backdate the move
        move = Move.objects.filter(reason="d1:2026-03-20").first()
        Move.objects.filter(pk=move.pk).update(
            timestamp=move.timestamp - timedelta(days=3)
        )

        out = StringIO()
        call_command("cleanup_d1", stdout=out)

        quant = Quant.objects.get(sku="PAO-FRANCES", position=self.ontem_pos)
        self.assertEqual(quant._quantity, Decimal("0"))
        self.assertIn("Removido", out.getvalue())

    def test_cleanup_d1_idempotent_on_zero_qty(self):
        # Create and immediately drain
        StockMovements.receive(Decimal("5"), "PAO-FRANCES", position=self.ontem_pos, reason="d1:2026-03-20")
        quant = Quant.objects.get(sku="PAO-FRANCES", position=self.ontem_pos)
        StockMovements.issue(Decimal("5"), quant, reason="manual")

        move = Move.objects.filter(reason="d1:2026-03-20").first()
        Move.objects.filter(pk=move.pk).update(
            timestamp=move.timestamp - timedelta(days=3)
        )

        out = StringIO()
        call_command("cleanup_d1", stdout=out)
        # qty is 0, so command skips entirely (no stock to clean)
        self.assertNotIn("Removido", out.getvalue())


class DashboardD1WidgetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ontem_pos = Position.objects.create(
            ref="ontem", name="Ontem (D-1)", kind="logical",
            is_saleable=True,
        )
        cls.product = Product.objects.create(
            sku="PAO-FRANCES", name="Pão Francês", base_price_q=150,
        )

    def test_dashboard_shows_d1_widget_when_stock_exists(self):
        StockMovements.receive(Decimal("5"), "PAO-FRANCES", position=self.ontem_pos, reason="d1:2026-03-27")

        rows = _d1_stock()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sku"], "PAO-FRANCES")
        self.assertEqual(rows[0]["qty"], Decimal("5"))

        table = _build_d1_table(rows)
        self.assertEqual(len(table["rows"]), 1)
        self.assertEqual(table["headers"], ["SKU", "Produto", "Qtd", "Entrada"])

    def test_dashboard_hides_d1_widget_when_empty(self):
        rows = _d1_stock()
        self.assertEqual(rows, [])
