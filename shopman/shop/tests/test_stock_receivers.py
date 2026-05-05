from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone
from shopman.guestman.models import Customer
from shopman.offerman.models import Product
from shopman.orderman.models import Session
from shopman.stockman import HoldStatus
from shopman.stockman.models import Hold

from shopman.shop.handlers._stock_receivers import on_holds_materialized


@pytest.mark.django_db
@override_settings(SHOPMAN_BASE_URL="https://shop.example")
def test_holds_materialized_notifies_customer_with_deadline_and_cart_url():
    customer = Customer.objects.create(
        ref="CUS-STOCK-ARRIVED",
        first_name="Ana",
        phone="5543999990011",
    )
    product = Product.objects.create(
        sku="FERMATA-001",
        name="Croissant de fermentação longa",
        base_price_q=1200,
        is_published=True,
        is_sellable=True,
    )
    session = Session.objects.create(
        session_key="sess-stock-arrived",
        channel_ref="web",
        data={"customer_id": str(customer.uuid)},
    )
    deadline = timezone.now() + timedelta(minutes=45)
    hold = Hold.objects.create(
        sku=product.sku,
        quantity=Decimal("1"),
        target_date=date.today(),
        status=HoldStatus.PENDING,
        expires_at=deadline,
        metadata={"reference": session.session_key, "planned": True},
    )

    with patch("shopman.shop.notifications.notify") as notify:
        on_holds_materialized(
            sender=None,
            hold_ids=[hold.hold_id],
            sku=product.sku,
            target_date=date.today(),
        )

    notify.assert_called_once()
    kwargs = notify.call_args.kwargs
    assert kwargs["event"] == "stock.arrived"
    assert kwargs["recipient"] == customer.phone
    assert kwargs["backend"] is None
    assert kwargs["context"]["sku"] == product.sku
    assert kwargs["context"]["product_name"] == product.name
    assert kwargs["context"]["deadline_at"] == deadline.isoformat()
    assert kwargs["context"]["cart_url"] == "https://shop.example/cart/"
    assert kwargs["context"]["session_key"] == session.session_key


@pytest.mark.django_db
def test_holds_materialized_without_customer_is_silent():
    session = Session.objects.create(
        session_key="sess-no-customer",
        channel_ref="web",
        data={},
    )
    hold = Hold.objects.create(
        sku="FERMATA-ANON",
        quantity=Decimal("1"),
        target_date=date.today(),
        status=HoldStatus.PENDING,
        expires_at=timezone.now() + timedelta(minutes=30),
        metadata={"reference": session.session_key, "planned": True},
    )

    with patch("shopman.shop.notifications.notify") as notify:
        on_holds_materialized(
            sender=None,
            hold_ids=[hold.hold_id],
            sku=hold.sku,
            target_date=date.today(),
        )

    notify.assert_not_called()


@pytest.mark.django_db
@override_settings(SHOPMAN_BASE_URL="https://shop.example")
def test_holds_materialized_honours_enabled_email_channel():
    customer = Customer.objects.create(
        ref="CUS-STOCK-EMAIL",
        first_name="Bia",
        phone="5543999990022",
        email="bia@example.test",
    )
    product = Product.objects.create(
        sku="FERMATA-EMAIL",
        name="Brioche reservado",
        base_price_q=1500,
        is_published=True,
        is_sellable=True,
    )
    session = Session.objects.create(
        session_key="sess-stock-email",
        channel_ref="web",
        data={"customer_ref": customer.ref},
    )
    hold = Hold.objects.create(
        sku=product.sku,
        quantity=Decimal("1"),
        target_date=date.today(),
        status=HoldStatus.PENDING,
        expires_at=timezone.now() + timedelta(minutes=30),
        metadata={"reference": session.session_key, "planned": True},
    )

    with patch(
        "shopman.shop.services.customer_context.enabled_notification_channels",
        return_value=frozenset({"email"}),
    ), patch("shopman.shop.notifications.notify") as notify:
        on_holds_materialized(
            sender=None,
            hold_ids=[hold.hold_id],
            sku=product.sku,
            target_date=date.today(),
        )

    notify.assert_called_once()
    kwargs = notify.call_args.kwargs
    assert kwargs["backend"] == "email"
    assert kwargs["recipient"] == customer.email
