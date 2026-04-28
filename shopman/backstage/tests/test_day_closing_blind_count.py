from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from shopman.backstage.models import DayClosing
from shopman.offerman.models import Product
from shopman.stockman import Position, Quant
from shopman.stockman.services.movements import StockMovements


def _make_shop():
    from shopman.shop.models import Shop

    return Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})[0]


def _grant_closing_perm(user):
    ct = ContentType.objects.get_for_model(DayClosing)
    perm = Permission.objects.get(content_type=ct, codename="perform_closing")
    user.user_permissions.add(perm)


class DayClosingBlindCountTests(TestCase):
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

    def test_closing_form_is_blind_count_for_operator(self) -> None:
        resp = self.client.get("/gestor/fechamento/")

        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn(
            "Informe apenas o que sobrou fisicamente. "
            "O sistema trata destino e perdas automaticamente.",
            content,
        )
        self.assertIn("Sobraram", content)
        self.assertNotIn("Disponível", content)
        self.assertNotIn("Tipo", content)
        self.assertNotIn("D-1", content)
        self.assertNotIn('max="2"', content)

    def test_closing_records_reported_and_applied_quantities_without_silent_clamp(self) -> None:
        resp = self.client.post("/gestor/fechamento/", {f"qty_{self.product.sku}": "5"})

        self.assertEqual(resp.status_code, 302)
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
