"""Tests for WP-R12 — POS Manual Discount + Item Notes."""

from __future__ import annotations

from django.test import TestCase
from shopman.orderman.ids import generate_session_key
from shopman.orderman.models import Session
from shopman.orderman.services.modify import ModifyService

from shopman.shop.models import Channel


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
