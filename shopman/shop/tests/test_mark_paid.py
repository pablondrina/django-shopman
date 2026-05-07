"""Guardrails for the removed operator hot-path mark-paid shortcut."""

from __future__ import annotations

from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from shopman.backstage.services import orders as backstage_orders
from shopman.shop.models import Shop
from shopman.shop.services import operator_orders

ROOT = Path(__file__).resolve().parents[3]


class OperatorMarkPaidShortcutTests(TestCase):
    def test_mark_paid_route_name_is_not_registered(self) -> None:
        with self.assertRaises(NoReverseMatch):
            reverse("backstage:gestor_mark_paid", kwargs={"ref": "ORD-1"})

    def test_mark_paid_endpoint_is_not_reachable(self) -> None:
        Shop.objects.create(name="Test Shop", default_ddd="11", currency="BRL", timezone="America/Sao_Paulo")
        user = get_user_model().objects.create_superuser("mark-paid-admin", password="pw")
        self.client.force_login(user)

        response = self.client.post("/admin/operacao/pedidos/ORD-1/marcar-pago/")

        self.assertEqual(response.status_code, 404)

    def test_operator_command_services_do_not_export_mark_paid(self) -> None:
        self.assertFalse(hasattr(backstage_orders, "mark_paid"))
        self.assertFalse(hasattr(operator_orders, "mark_paid"))

    def test_operator_hot_path_surfaces_do_not_expose_mark_paid_action(self) -> None:
        files = (
            ROOT / "shopman/backstage/urls.py",
            ROOT / "shopman/backstage/admin_console/orders.py",
            ROOT / "shopman/backstage/services/orders.py",
            ROOT / "shopman/shop/services/operator_orders.py",
            ROOT / "shopman/backstage/templates/admin_console/orders/cells/actions.html",
        )

        for path in files:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("mark-paid", text)
                self.assertNotIn("mark_paid", text)
