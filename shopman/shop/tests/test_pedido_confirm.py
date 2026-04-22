from __future__ import annotations

from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from shopman.orderman.models import Order

from shopman.shop.models import Channel


class PedidoConfirmTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.staff = User.objects.create_user("staff_confirm", password="pw", is_staff=True)
        ct = ContentType.objects.get(app_label="shop", model="shop")
        perm = Permission.objects.get(content_type=ct, codename="manage_orders")
        self.staff.user_permissions.add(perm)
        self.client.force_login(self.staff)
        Channel.objects.create(ref="pdv", name="Balcao", is_active=True)

    def test_confirm_requires_positive_availability_decision(self) -> None:
        order = Order.objects.create(
            ref="ORD-CONF-001",
            channel_ref="pdv",
            session_key="sess-confirm-001",
            status=Order.Status.NEW,
            snapshot={"items": [{"sku": "TEST-SKU", "qty": 1}], "data": {}},
            data={},
            total_q=1500,
        )

        resp = self.client.post(f"/pedidos/{order.ref}/confirm/")

        self.assertEqual(resp.status_code, 422)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.NEW)

    def test_confirm_succeeds_with_positive_availability_decision(self) -> None:
        order = Order.objects.create(
            ref="ORD-CONF-002",
            channel_ref="pdv",
            session_key="sess-confirm-002",
            status=Order.Status.NEW,
            snapshot={"items": [{"sku": "TEST-SKU", "qty": 1}], "data": {}},
            data={
                "availability_decision": {
                    "approved": True,
                    "source": "test",
                    "decisions": [{"sku": "TEST-SKU", "requested_qty": 1}],
                }
            },
            total_q=1500,
        )

        resp = self.client.post(f"/pedidos/{order.ref}/confirm/")

        self.assertEqual(resp.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)
