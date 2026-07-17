from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from shopman.offerman.models import Product
from shopman.stockman import Position, Quant
from shopman.stockman.services.movements import StockMovements

from shopman.backstage.models import DayClosing


def _make_shop():
    from shopman.shop.models import Shop

    return Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})[0]


def _grant_closing_perm(user):
    ct = ContentType.objects.get_for_model(DayClosing)
    perm = Permission.objects.get(content_type=ct, codename="perform_closing")
    user.user_permissions.add(perm)


class DayClosingBlindCountTests(TestCase):
    """Contagem cega via a API headless do fechamento (antesala do PDV).

    A tela Admin/Unfold foi removida (ADMIN-ROLE-PLAN WP-ADM-3); a superfície é
    `pos-nuxt /session/closing` sobre `GET/POST /api/v1/backstage/closing/`. A
    cegueira visual (não exibir o disponível ao operador) é contrato da PÁGINA
    (vitest do pos-nuxt); aqui garantimos a semântica do registro: reported vs
    applied sem clamp silencioso, destino "Ontem" e o gate por permissão.
    """

    def setUp(self) -> None:
        _make_shop()
        User = get_user_model()
        self.staff = User.objects.create_user(username="closing", password="x", is_staff=True)
        _grant_closing_perm(self.staff)
        self.client.force_login(self.staff)

        self.loja = Position.objects.create(ref="loja", name="Loja", is_saleable=True)
        self.ontem = Position.objects.create(ref="ontem", name="Ontem", is_saleable=False)
        self.product = Product.objects.create(
            sku="PAO-TESTE",
            name="Pão Teste",
            metadata={"allows_next_day_sale": True},
        )
        StockMovements.receive(
            quantity=2,
            sku=self.product.sku,
            position=self.loja,
            reason="seed test",
        )

    def test_closing_projection_lists_items_with_classification(self) -> None:
        resp = self.client.get("/api/v1/backstage/closing/")

        self.assertEqual(resp.status_code, 200)
        closing = resp.json()["closing"]
        self.assertFalse(closing["already_closed"])
        item = next(it for it in closing["items"] if it["sku"] == self.product.sku)
        self.assertEqual(item["classification"], "d1")

    def test_closing_api_requires_perform_closing_permission(self) -> None:
        User = get_user_model()
        other = User.objects.create_user(username="no-perm", password="x", is_staff=True)
        self.client.force_login(other)

        resp = self.client.get("/api/v1/backstage/closing/")

        self.assertEqual(resp.status_code, 403)

    def test_closing_records_reported_and_applied_quantities_without_silent_clamp(self) -> None:
        resp = self.client.post(
            "/api/v1/backstage/closing/",
            {"quantities": {self.product.sku: "5"}},
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        closing = DayClosing.objects.get()
        row = closing.data["items"][0]
        self.assertEqual(row["sku"], self.product.sku)
        self.assertEqual(row["qty_reported"], 5)
        self.assertEqual(row["qty_applied"], 2)
        self.assertEqual(row["qty_discrepancy"], 3)
        self.assertEqual(row["qty_d1"], 2)

        saleable = Quant.objects.get(sku=self.product.sku, position=self.loja)
        d1 = Quant.objects.get(sku=self.product.sku, position=self.ontem, batch="D-1")
        self.assertEqual(saleable.quantity, 0)
        self.assertEqual(d1.quantity, 2)

    def test_closing_twice_returns_conflict(self) -> None:
        first = self.client.post(
            "/api/v1/backstage/closing/",
            {"quantities": {self.product.sku: "0"}},
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 200)

        second = self.client.post(
            "/api/v1/backstage/closing/",
            {"quantities": {self.product.sku: "0"}},
            content_type="application/json",
        )

        self.assertEqual(second.status_code, 409)
        self.assertEqual(DayClosing.objects.count(), 1)

    def test_admin_day_closing_route_is_gone(self) -> None:
        with self.assertRaises(NoReverseMatch):
            reverse("admin_console_day_closing")
