"""Category 4 (follow-up) — the coupon over-redemption race is *observable*.

Design: under a true concurrency race two carts can both commit with a
single-use coupon's discount already sealed into their order snapshot. The
atomic CAS (`record_coupon_use`) caps ``uses_count`` at ``max_uses`` (never
over-counts), and the loser of the race — whose sale already went out with the
discount — must raise an operator alert so the house can reconcile.

These tests lock that safety net deterministically (no threads): they drive
``_record_coupon_use`` against an order whose snapshot carries the coupon
discount while the coupon is already at its cap, and assert:
- ``uses_count`` is NOT pushed past ``max_uses``;
- an ``OperatorAlert(type="coupon_over_redeemed")`` is created;
- that alert type is registered, so it surfaces with a human label in the
  operator console (not a raw slug the operator can't read).
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.backstage.models import OperatorAlert
from shopman.shop.lifecycle import _record_coupon_use
from shopman.shop.models import Channel, Shop
from shopman.storefront.models import Coupon, Promotion

pytestmark = pytest.mark.django_db


@pytest.fixture
def _shop_channel(db):
    Shop.objects.create(name="Test Shop", brand_name="Test")
    return Channel.objects.create(ref="web", name="Web")


def _exhausted_coupon(code: str) -> Coupon:
    now = timezone.now()
    promo = Promotion.objects.create(
        name=f"Promo {code}",
        type=Promotion.FIXED,
        value=500,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
    )
    # Already at its cap — a concurrent commit won the race first.
    return Coupon.objects.create(code=code, promotion=promo, max_uses=1, uses_count=1)


def _order_with_coupon_snapshot(code: str) -> Order:
    return Order.objects.create(
        ref=f"ORD-OVR-{code}",
        channel_ref="web",
        status="new",
        total_q=2000,
        handle_type="phone",
        handle_ref="+5543999990001",
        data={},
        snapshot={"pricing": {"coupon": {"code": code, "discount_q": 500}}},
    )


def test_over_redeem_raises_operator_alert_and_caps_count(_shop_channel):
    coupon = _exhausted_coupon("OVR1")
    order = _order_with_coupon_snapshot("OVR1")

    _record_coupon_use(order)

    coupon.refresh_from_db()
    assert coupon.uses_count == 1, "atomic cap breached — uses_count exceeded max_uses"

    alerts = OperatorAlert.objects.filter(type="coupon_over_redeemed", order_ref=order.ref)
    assert alerts.exists(), "no operator alert raised for an over-redeemed coupon"
    # The race loser did not get a phantom `coupon_use_recorded` marker (nothing
    # to release on cancel — the count belongs to the winner).
    order.refresh_from_db()
    assert "coupon_use_recorded" not in (order.data or {})


def test_over_redeem_alert_type_is_registered_for_operator(_shop_channel):
    """The alert must render with a human label in the operator console — a raw
    unregistered slug would make the reconciliation cue unreadable."""
    coupon = _exhausted_coupon("OVR2")
    order = _order_with_coupon_snapshot("OVR2")

    _record_coupon_use(order)

    alert = OperatorAlert.objects.filter(type="coupon_over_redeemed", order_ref=order.ref).first()
    assert alert is not None
    label = alert.get_type_display()
    assert label and label != "coupon_over_redeemed", (
        f"alert type not registered in OperatorAlert.TYPE_CHOICES: display={label!r}"
    )
    assert coupon.code in alert.message


def test_within_cap_records_use_and_no_alert(_shop_channel):
    """Control: when the coupon is still under its cap, the use is counted and
    NO over-redemption alert fires."""
    now = timezone.now()
    promo = Promotion.objects.create(
        name="Ok", type=Promotion.FIXED, value=500,
        valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1),
    )
    coupon = Coupon.objects.create(code="OKAY", promotion=promo, max_uses=5, uses_count=0)
    order = _order_with_coupon_snapshot("OKAY")

    _record_coupon_use(order)

    coupon.refresh_from_db()
    assert coupon.uses_count == 1
    assert not OperatorAlert.objects.filter(type="coupon_over_redeemed").exists()
    order.refresh_from_db()
    assert order.data.get("coupon_use_recorded") == "OKAY"
