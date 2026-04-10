"""Tests for WP-R12 — POS Manual Discount + Item Notes."""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from shopman.omniman.ids import generate_session_key
from shopman.omniman.models import Session
from shopman.omniman.services.modify import ModifyService
from shopman.models import Channel


def _make_channel():
    return Channel.objects.get_or_create(
        ref="balcao",
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
                defaults={"name": item["sku"], "base_price_q": item["unit_price_q"], "is_published": True, "is_available": True},
            )
        ModifyService.modify_session(
            session_key=session_key,
            channel_ref="balcao",
            ops=[{"op": "add_line", "sku": i["sku"], "qty": i["qty"], "unit_price_q": i["unit_price_q"]} for i in items],
        )
    session.refresh_from_db()
    return session


class ManualDiscountModifierTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        from shopman.models import Shop
        Shop.objects.create(name="Test Shop", brand_name="Test")

    def _apply_modifier(self, session, discount_q, reason="cortesia"):
        from shopman.modifiers import ManualDiscountModifier
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
        from shopman.models import Shop
        Shop.objects.create(name="Test Shop", brand_name="Test")
        _make_channel()
        from shopman.offerman.models import Product
        Product.objects.create(sku="POS-ITEM-1", name="Item 1", base_price_q=1000, is_published=True, is_available=True)
        User = get_user_model()
        self.staff = User.objects.create_user(username="pos_staff", password="x", is_staff=True)

    def _close_sale(self, items, manual_discount=None):
        payload = {
            "items": items,
            "customer_name": "",
            "customer_phone": "",
            "payment_method": "dinheiro",
            "manual_discount": manual_discount,
        }
        self.client.force_login(self.staff)
        return self.client.post(
            "/gestao/pos/close/",
            {"payload": json.dumps(payload)},
        )

    def test_close_without_discount(self) -> None:
        """POS close works without manual discount."""
        resp = self._close_sale([{"sku": "POS-ITEM-1", "qty": 1, "unit_price_q": 1000}])
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "pos-result")

    def test_close_with_discount_payload_accepted(self) -> None:
        """POS close accepts manual_discount in payload."""
        resp = self._close_sale(
            [{"sku": "POS-ITEM-1", "qty": 1, "unit_price_q": 1000, "note": "sem açúcar"}],
            manual_discount={"type": "percent", "value": 10, "discount_q": 100, "reason": "cortesia"},
        )
        self.assertEqual(resp.status_code, 200)

    def test_close_with_item_note(self) -> None:
        """Item note is accepted in payload (stored in meta)."""
        resp = self._close_sale([{"sku": "POS-ITEM-1", "qty": 1, "unit_price_q": 1000, "note": "extra picante"}])
        self.assertEqual(resp.status_code, 200)
