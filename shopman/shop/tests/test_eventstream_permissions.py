"""SSE channel permission tests."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from shopman.doorman.models import CustomerUser
from shopman.guestman.models import Customer
from shopman.orderman.models import Order

from shopman.shop.eventstream import ShopmanChannelManager

pytestmark = pytest.mark.django_db


def test_stock_channels_remain_public():
    manager = ShopmanChannelManager()

    assert manager.can_read_channel(None, "stock-web") is True


def test_backstage_channels_require_staff_user():
    manager = ShopmanChannelManager()
    customer_user = User.objects.create_user(username="customer")
    staff = User.objects.create_user(username="staff", is_staff=True)

    assert manager.can_read_channel(None, "backstage-orders-main") is False
    assert manager.can_read_channel(customer_user, "backstage-orders-main") is False
    assert manager.can_read_channel(staff, "backstage-orders-main") is True


def test_order_channels_require_matching_customer_or_staff():
    manager = ShopmanChannelManager()
    customer = Customer.objects.create(
        ref="CUST-SSE-001",
        first_name="Ana",
        phone="5543999990001",
    )
    matching_user = User.objects.create_user(username="ana")
    other_user = User.objects.create_user(username="other")
    staff = User.objects.create_user(username="ops", is_staff=True)
    CustomerUser.objects.create(user=matching_user, customer_id=customer.uuid)
    order = Order.objects.create(
        ref="ORD-SSE-001",
        channel_ref="web",
        status="new",
        total_q=1000,
        handle_type="phone",
        handle_ref=customer.phone,
        data={"customer_ref": customer.ref},
    )

    assert manager.can_read_channel(None, f"order-{order.ref}") is False
    assert manager.can_read_channel(other_user, f"order-{order.ref}") is False
    assert manager.can_read_channel(matching_user, f"order-{order.ref}") is True
    assert manager.can_read_channel(staff, f"order-{order.ref}") is True
