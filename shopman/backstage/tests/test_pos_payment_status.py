"""POS payment status endpoint — polling do PIX gateado por operate_pos.

O status endpoint do storefront é gateado pela sessão de checkout do CLIENTE
(anônima); o operador (staff) não se encaixa. Este é o equivalente operador para
o POS ver a confirmação do PIX chegar sem sair do balcão.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from shopman.orderman.models import Order

from shopman.shop.models import Shop

User = get_user_model()

STATUS_URL = "/api/v1/backstage/pos/payment/{ref}/status/"


def _grant_pos_perm(user):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    from shopman.backstage.models import CashShift

    ct = ContentType.objects.get_for_model(CashShift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename="operate_pos"))


@override_settings(SHOPMAN_REQUIRE_ACTIVE_OPERATOR=False)
class POSPaymentStatusTests(TestCase):
    def setUp(self):
        Shop.objects.create(name="Test", brand_name="Test")
        self.operator = User.objects.create_user("op", password="x", is_staff=True)
        _grant_pos_perm(self.operator)
        self.api = APIClient()
        self.api.force_authenticate(self.operator)

    def _order(self, ref: str, **data) -> Order:
        return Order.objects.create(
            ref=ref, channel_ref="pdv", status="new", total_q=1000,
            data={"payment": {"method": "pix"}, **data},
        )

    def test_reports_payment_status_shape(self):
        self._order("POS-PAY-1")
        resp = self.api.get(STATUS_URL.format(ref="POS-PAY-1"))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # O contrato que o POS consome para saber se o PIX confirmou.
        for key in ("is_paid", "is_cancelled", "is_terminal"):
            self.assertIn(key, body)
        self.assertFalse(body["is_paid"])  # pedido novo, PIX pendente

    def test_requires_operate_pos_permission(self):
        no_perm = User.objects.create_user("nobody", password="x", is_staff=True)
        c = APIClient()
        c.force_authenticate(no_perm)
        self._order("POS-PAY-2")
        resp = c.get(STATUS_URL.format(ref="POS-PAY-2"))
        self.assertEqual(resp.status_code, 403)

    def test_unknown_order_404(self):
        resp = self.api.get(STATUS_URL.format(ref="NOPE"))
        self.assertEqual(resp.status_code, 404)
