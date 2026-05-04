from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from shopman.orderman.models import Order

from shopman.shop.models import Channel, Shop


class OrderConfirmTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.staff = User.objects.create_user("staff_confirm", password="pw", is_staff=True)
        ct = ContentType.objects.get(app_label="shop", model="shop")
        perm = Permission.objects.get(content_type=ct, codename="manage_orders")
        self.staff.user_permissions.add(perm)
        self.client.force_login(self.staff)
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)
        Shop.objects.create(  # required: OnboardingMiddleware redirects operator pages if no Shop
            name="Test Shop", default_ddd="11", currency="BRL", timezone="America/Sao_Paulo"
        )

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

        resp = self.client.post(f"/admin/operacao/pedidos/{order.ref}/confirmar/")

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

        resp = self.client.post(f"/admin/operacao/pedidos/{order.ref}/confirmar/")

        self.assertEqual(resp.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)

    def test_confirm_blocks_pending_digital_payment(self) -> None:
        Channel.objects.create(
            ref="web-pay",
            name="Web Pay",
            is_active=True,
            config={
                "confirmation": {"mode": "manual"},
                "payment": {"method": "pix", "timing": "at_commit"},
            },
        )
        order = Order.objects.create(
            ref="ORD-CONF-PAY-001",
            channel_ref="web-pay",
            session_key="sess-confirm-pay-001",
            status=Order.Status.NEW,
            snapshot={"items": [{"sku": "TEST-SKU", "qty": 1}], "data": {}},
            data={
                "payment": {"method": "pix", "intent_ref": "PAY-PENDING"},
                "availability_decision": {
                    "approved": True,
                    "source": "test",
                    "decisions": [{"sku": "TEST-SKU", "requested_qty": 1}],
                },
            },
            total_q=1500,
        )

        with patch("shopman.shop.services.payment.get_payment_status", return_value="pending"):
            resp = self.client.post(f"/admin/operacao/pedidos/{order.ref}/confirmar/")

        self.assertEqual(resp.status_code, 422)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.NEW)

    def test_confirm_blocks_refunded_digital_payment_without_captured_balance(self) -> None:
        Channel.objects.create(
            ref="web-refunded",
            name="Web Refunded",
            is_active=True,
            config={
                "confirmation": {"mode": "manual"},
                "payment": {"method": "pix", "timing": "at_commit"},
            },
        )
        order = Order.objects.create(
            ref="ORD-CONF-REFUNDED-001",
            channel_ref="web-refunded",
            session_key="sess-confirm-refunded-001",
            status=Order.Status.NEW,
            snapshot={"items": [{"sku": "TEST-SKU", "qty": 1}], "data": {}},
            data={
                "payment": {"method": "pix", "intent_ref": "PAY-REFUNDED"},
                "availability_decision": {
                    "approved": True,
                    "source": "test",
                    "decisions": [{"sku": "TEST-SKU", "requested_qty": 1}],
                },
            },
            total_q=1500,
        )

        with (
            patch("shopman.shop.services.payment.get_payment_status", return_value="refunded"),
            patch("shopman.shop.services.payment._payman_captured_balance_q", return_value=0),
        ):
            resp = self.client.post(f"/admin/operacao/pedidos/{order.ref}/confirmar/")

        self.assertEqual(resp.status_code, 422)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.NEW)

    def test_confirm_endpoint_rejects_non_new_order_shortcut(self) -> None:
        order = Order.objects.create(
            ref="ORD-CONF-BLOCKED-STATUS",
            channel_ref="pdv",
            session_key="sess-confirm-blocked-status",
            status=Order.Status.CONFIRMED,
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

        resp = self.client.post(f"/admin/operacao/pedidos/{order.ref}/confirmar/")

        self.assertEqual(resp.status_code, 422)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)
