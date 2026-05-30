"""Tests for WP-R12 — POS Manual Discount + Item Notes."""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from shopman.orderman.ids import generate_session_key
from shopman.orderman.models import Order, Session
from shopman.orderman.services.modify import ModifyService

from shopman.backstage.models import POSTab
from shopman.shop.models import Channel
from shopman.shop.services import pos as pos_service


def _make_channel():
    return Channel.objects.get_or_create(
        ref="pdv",
        defaults={"name": "Balcão", "is_active": True},
    )[0]


def _make_session(items=None):
    channel = _make_channel()
    session_key = generate_session_key()
    session = Session.objects.create(
        session_key=session_key,
        channel_ref=channel.ref,
        state="open",
        pricing_policy="fixed",
        edit_policy="open",
    )
    if items:
        from shopman.offerman.models import Product
        for item in items:
            Product.objects.get_or_create(
                sku=item["sku"],
                defaults={"name": item["sku"], "base_price_q": item["unit_price_q"], "is_published": True, "is_sellable": True},
            )
        ModifyService.modify_session(
            session_key=session_key,
            channel_ref="pdv",
            ops=[{"op": "add_line", "sku": i["sku"], "qty": i["qty"], "unit_price_q": i["unit_price_q"]} for i in items],
        )
    session.refresh_from_db()
    return session



def _grant_pos_perm(user):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    from shopman.backstage.models import CashShift
    ct = ContentType.objects.get_for_model(CashShift)
    perm = Permission.objects.get(content_type=ct, codename="operate_pos")
    user.user_permissions.add(perm)


def _grant_adjust_cashshift_perm(user):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    from shopman.backstage.models import CashShift
    ct = ContentType.objects.get_for_model(CashShift)
    perm = Permission.objects.get(content_type=ct, codename="adjust_cashshift")
    user.user_permissions.add(perm)


class ManualDiscountModifierTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        from shopman.shop.models import Shop
        Shop.objects.create(name="Test Shop", brand_name="Test")

    def _apply_modifier(self, session, discount_q, reason="cortesia"):
        from shopman.shop.modifiers import ManualDiscountModifier
        data = session.data or {}
        data["manual_discount"] = {"discount_q": discount_q, "reason": reason}
        session.data = data
        session.save(update_fields=["data"])
        session.refresh_from_db()

        modifier = ManualDiscountModifier()
        from unittest.mock import MagicMock
        modifier.apply(channel=MagicMock(), session=session, ctx={})
        session.refresh_from_db()
        return session

    def test_noop_when_zero_discount(self) -> None:
        """No discount applied when discount_q == 0."""
        session = _make_session(items=[{"sku": "POS-DISC-A", "qty": 1, "unit_price_q": 1000}])
        session = self._apply_modifier(session, discount_q=0)
        self.assertNotIn("manual_discount", session.pricing or {})

    def test_discount_percent_applied(self) -> None:
        """Manual discount persisted in session.pricing['manual_discount']."""
        session = _make_session(items=[{"sku": "POS-DISC-B", "qty": 1, "unit_price_q": 1000}])
        session = self._apply_modifier(session, discount_q=200, reason="cortesia")

        pricing = session.pricing or {}
        self.assertIn("manual_discount", pricing)
        self.assertEqual(pricing["manual_discount"]["total_discount_q"], 200)
        self.assertIn("cortesia", pricing["manual_discount"]["label"])

    def test_discount_clamped_to_subtotal(self) -> None:
        """Discount is clamped to order subtotal (never negative)."""
        session = _make_session(items=[{"sku": "POS-DISC-C", "qty": 1, "unit_price_q": 500}])
        session = self._apply_modifier(session, discount_q=2000)

        pricing = session.pricing or {}
        self.assertLessEqual(pricing["manual_discount"]["total_discount_q"], 500)


class POSCloseWithDiscountTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        from shopman.shop.models import Shop
        Shop.objects.create(name="Test Shop", brand_name="Test")
        _make_channel()
        from shopman.offerman.models import Product
        Product.objects.create(sku="POS-ITEM-1", name="Item 1", base_price_q=1000, is_published=True, is_sellable=True)
        User = get_user_model()
        self.staff = User.objects.create_user(username="pos_staff", password="x", is_staff=True)
        _grant_pos_perm(self.staff)
        from shopman.backstage.models import CashShift, POSTerminal

        CashShift.objects.create(
            operator=self.staff,
            terminal=POSTerminal.default(),
            opening_amount_q=0,
        )

    def _close_sale(self, items, manual_discount=None, manager_approval=None):
        POSTab.objects.get_or_create(ref="00001007", defaults={"label": "1007"})
        opened = pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_ref="1007",
            actor=f"pos:{self.staff.username}",
            operator_username=self.staff.username,
        )
        payload = {
            "items": items,
            "customer_name": "",
            "customer_phone": "",
            "payment_method": "cash",
            "manual_discount": manual_discount,
            "manager_approval": manager_approval,
            "tab_ref": opened["tab_ref"],
            "tab_session_key": opened["tab_session_key"],
        }
        self.client.force_login(self.staff)
        return self.client.post(
            "/gestor/pos/close/",
            {"payload": json.dumps(payload)},
        )

    def test_close_without_discount(self) -> None:
        """POS close works without manual discount."""
        resp = self._close_sale([{"sku": "POS-ITEM-1", "qty": 1, "unit_price_q": 1000}])
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "data-order-ref")

    def test_close_with_discount_payload_accepted(self) -> None:
        """POS close accepts manual_discount in payload."""
        resp = self._close_sale(
            [{"sku": "POS-ITEM-1", "qty": 1, "unit_price_q": 1000, "notes": "sem açúcar"}],
            manual_discount={"type": "percent", "value": 10, "discount_q": 100, "reason": "cortesia"},
        )
        self.assertEqual(resp.status_code, 200)

    @override_settings(SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q=50)
    def test_close_with_discount_requires_manager_approval_when_configured(self) -> None:
        resp = self._close_sale(
            [{"sku": "POS-ITEM-1", "qty": 1, "unit_price_q": 1000}],
            manual_discount={"type": "percent", "value": 10, "discount_q": 100, "reason": "cortesia"},
        )

        self.assertEqual(resp.status_code, 422)
        self.assertIn("aprovação gerencial", resp.content.decode().lower())

    @override_settings(SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q=50)
    def test_close_with_discount_accepts_manager_approval(self) -> None:
        from shopman.doorman.models import PinCredential

        User = get_user_model()
        manager = User.objects.create_user(username="pos_manager", password="secret", is_staff=True)
        _grant_adjust_cashshift_perm(manager)
        PinCredential.set_for(manager, "4321")

        resp = self._close_sale(
            [{"sku": "POS-ITEM-1", "qty": 1, "unit_price_q": 1000}],
            manual_discount={"type": "percent", "value": 10, "discount_q": 100, "reason": "cortesia"},
            manager_approval={"username": "pos_manager", "pin": "4321"},
        )

        self.assertEqual(resp.status_code, 200)
        order = Order.objects.latest("created_at")
        self.assertEqual(order.data["manual_discount"]["approved_by"], "pos_manager")

    @override_settings(SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q=50)
    def test_close_with_discount_rejects_wrong_manager_pin(self) -> None:
        from shopman.doorman.models import PinCredential

        User = get_user_model()
        manager = User.objects.create_user(username="pos_manager", password="secret", is_staff=True)
        _grant_adjust_cashshift_perm(manager)
        PinCredential.set_for(manager, "4321")

        resp = self._close_sale(
            [{"sku": "POS-ITEM-1", "qty": 1, "unit_price_q": 1000}],
            manual_discount={"type": "percent", "value": 10, "discount_q": 100, "reason": "cortesia"},
            manager_approval={"username": "pos_manager", "pin": "0000"},
        )

        self.assertEqual(resp.status_code, 422)
        self.assertIn("aprovação gerencial", resp.content.decode().lower())

    def test_close_with_item_note(self) -> None:
        """Item notes are accepted in payload and stored in canonical meta."""
        resp = self._close_sale([{"sku": "POS-ITEM-1", "qty": 1, "unit_price_q": 1000, "notes": "extra picante"}])
        self.assertEqual(resp.status_code, 200)
        order = Order.objects.latest("created_at")
        self.assertEqual(order.items.get().meta, {"notes": "extra picante"})
