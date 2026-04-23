"""
Tests for POS cancellation + granular errors — WP-R5.

Covers:
- cancel-last happy path
- cancel-last >5min rejected
- cancel-last staff-only
- cancel-last unknown ref → 404
- cancel-last wrong status → 422
- pos_close granular error messages
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from shopman.orderman.ids import generate_idempotency_key, generate_session_key
from shopman.orderman.models import Order, Session
from shopman.orderman.services.commit import CommitService
from shopman.orderman.services.modify import ModifyService

from shopman.shop.models import Channel


def _create_pos_order(payment_method: str = "dinheiro") -> Order:
    channel = Channel.objects.get(ref="pdv")
    session_key = generate_session_key()
    Session.objects.create(
        session_key=session_key,
        channel_ref=channel.ref,
        state="open",
        pricing_policy="fixed",
        edit_policy="open",
        handle_type="pos",
        handle_ref="pos:test",
    )
    ModifyService.modify_session(
        session_key=session_key,
        channel_ref="pdv",
        ops=[
            {"op": "add_line", "sku": "TEST-SKU", "qty": 1, "unit_price_q": 1000},
            {"op": "set_data", "path": "payment.method", "value": payment_method},
            {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
        ],
        ctx={"actor": "test"},
    )
    result = CommitService.commit(
        session_key=session_key,
        channel_ref="pdv",
        idempotency_key=generate_idempotency_key(),
        ctx={"actor": "test"},
    )
    return Order.objects.get(ref=result.order_ref)



def _grant_pos_perm(user):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType
    from shopman.backstage.models import CashRegisterSession
    ct = ContentType.objects.get_for_model(CashRegisterSession)
    perm = Permission.objects.get(content_type=ct, codename="operate_pos")
    user.user_permissions.add(perm)


class PosCancelLastTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        from shopman.shop.models import Shop
        Shop.objects.create(name="Test Shop", brand_name="Test")
        self.staff = User.objects.create_user("staff_user", password="pw", is_staff=True)
        _grant_pos_perm(self.staff)
        self.regular = User.objects.create_user("regular_user", password="pw", is_staff=False)
        self.channel = Channel.objects.create(
            ref="pdv",
            name="Balcão",
            is_active=True,
        )
        self.client.force_login(self.staff)

    def test_cancel_last_happy_path(self) -> None:
        """POST cancel-last within 5min → order cancelled."""
        order = _create_pos_order()
        resp = self.client.post("/gestor/pos/cancel-last/", {"order_ref": order.ref})

        self.assertEqual(resp.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "cancelled")

    def test_cancel_last_success_message(self) -> None:
        """Successful cancellation returns feedback with order ref."""
        order = _create_pos_order()
        resp = self.client.post("/gestor/pos/cancel-last/", {"order_ref": order.ref})

        self.assertContains(resp, order.ref)
        self.assertContains(resp, "cancelada")

    def test_cancel_last_too_old_rejected(self) -> None:
        """Order older than 5min → 422, not cancelled."""
        order = _create_pos_order()
        # Backdate the order by 6 minutes
        Order.objects.filter(pk=order.pk).update(
            created_at=timezone.now() - timedelta(minutes=6)
        )

        resp = self.client.post("/gestor/pos/cancel-last/", {"order_ref": order.ref})

        self.assertEqual(resp.status_code, 422)
        order.refresh_from_db()
        self.assertNotEqual(order.status, "cancelled")

    def test_cancel_last_staff_only(self) -> None:
        """Non-staff user → 403."""
        order = _create_pos_order()
        self.client.force_login(self.regular)

        resp = self.client.post("/gestor/pos/cancel-last/", {"order_ref": order.ref})
        self.assertEqual(resp.status_code, 403)

    def test_cancel_last_unknown_ref(self) -> None:
        """Unknown order ref → 404."""
        resp = self.client.post("/gestor/pos/cancel-last/", {"order_ref": "NONEXISTENT"})
        self.assertEqual(resp.status_code, 404)

    def test_cancel_last_wrong_status(self) -> None:
        """Order in terminal status → 422."""
        order = _create_pos_order()
        # Force to completed (terminal) bypassing transition rules
        Order.objects.filter(pk=order.pk).update(status="completed")

        resp = self.client.post("/gestor/pos/cancel-last/", {"order_ref": order.ref})
        self.assertEqual(resp.status_code, 422)

    def test_cancel_last_missing_ref(self) -> None:
        """POST without order_ref → 422."""
        resp = self.client.post("/gestor/pos/cancel-last/", {})
        self.assertEqual(resp.status_code, 422)


class PosCloseGranularErrorTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        from shopman.shop.models import Shop
        Shop.objects.create(name="Test Shop", brand_name="Test")
        self.staff = User.objects.create_user("staff_user", password="pw", is_staff=True)
        _grant_pos_perm(self.staff)
        self.channel = Channel.objects.create(
            ref="pdv",
            name="Balcão",
            is_active=True,
        )
        self.client.force_login(self.staff)

    def _close_payload(self, items=None, payment_method: str = "dinheiro") -> dict:
        import json
        if items is None:
            items = [{"sku": "TEST-SKU", "qty": 1, "unit_price_q": 1000}]
        return {
            "payload": json.dumps({
                "items": items,
                "payment_method": payment_method,
                "customer_name": "",
                "customer_phone": "",
            })
        }

    def test_pos_close_channel_not_found(self) -> None:
        """No pdv channel → 500 with channel error message."""
        self.channel.delete()

        resp = self.client.post("/gestor/pos/close/", self._close_payload())
        self.assertEqual(resp.status_code, 500)
        self.assertIn("pdv", resp.content.decode().lower())

    def test_pos_close_empty_cart(self) -> None:
        """Empty items list → 422."""
        import json
        resp = self.client.post("/gestor/pos/close/", {"payload": json.dumps({"items": []})})
        self.assertEqual(resp.status_code, 422)

    def test_pos_close_invalid_payload(self) -> None:
        """Non-JSON payload → 400."""
        resp = self.client.post("/gestor/pos/close/", {"payload": "not-json"})
        self.assertEqual(resp.status_code, 400)

    def test_pos_close_missing_payload(self) -> None:
        """No payload key → 422."""
        resp = self.client.post("/gestor/pos/close/", {})
        self.assertEqual(resp.status_code, 422)

    def test_pos_close_commit_error_returns_granular_message(self) -> None:
        """CommitService failure → error partial with detail message."""
        with patch("shopman.backstage.views.pos.CommitService.commit") as mock_commit:
            mock_commit.side_effect = Exception("Sessão expirada")

            resp = self.client.post("/gestor/pos/close/", self._close_payload())

        self.assertEqual(resp.status_code, 400)
        self.assertIn("Erro ao finalizar", resp.content.decode())

    def test_pos_close_modify_error_stock_message(self) -> None:
        """ModifyService failure with stock keyword → stock-specific message."""
        with patch("shopman.backstage.views.pos.ModifyService.modify_session") as mock_modify:
            mock_modify.side_effect = Exception("Estoque insuficiente para SKU X")

            resp = self.client.post("/gestor/pos/close/", self._close_payload())

        self.assertEqual(resp.status_code, 422)
        content = resp.content.decode()
        self.assertIn("indispon", content.lower())
