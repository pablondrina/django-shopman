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
@override_settings(SHOPMAN_STOREFRONT_BASE_URL="https://shop.example")
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
    assert kwargs["context"]["cart_url"] == "https://shop.example/cart"
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
@override_settings(SHOPMAN_STOREFRONT_BASE_URL="https://shop.example")
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
        "shopman.shop.projections.customer_context.enabled_notification_channels",
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


@pytest.mark.django_db
@override_settings(SHOPMAN_STOREFRONT_BASE_URL="https://shop.example")
def test_stock_arrived_renders_a_real_message_in_every_channel():
    """WP-D: prova o CORPO renderizado, não só o dispatch (o mock de notify
    escondia que nenhum canal tinha template de stock.arrived — o WhatsApp
    real mandava o fallback genérico "Notificacao: stock.arrived")."""
    from shopman.shop.adapters._notification_templates import render_message
    from shopman.shop.adapters.notification_email import (
        BODY_TEMPLATES,
        SUBJECT_TEMPLATES,
    )
    from shopman.shop.adapters.notification_manychat import (
        MESSAGE_TEMPLATES as MANYCHAT_TEMPLATES,
    )
    from shopman.shop.adapters.notification_sms import (
        MESSAGE_TEMPLATES as SMS_TEMPLATES,
    )

    customer = Customer.objects.create(
        ref="CUS-RENDER", first_name="Ana", phone="5543999990033",
    )
    product = Product.objects.create(
        sku="RENDER-001",
        name="Croissant de fermentação longa",
        base_price_q=1200,
        is_published=True,
        is_sellable=True,
    )
    session = Session.objects.create(
        session_key="sess-render",
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
            sender=None, hold_ids=[hold.hold_id], sku=product.sku, target_date=date.today(),
        )
    context = notify.call_args.kwargs["context"]

    local_deadline = timezone.localtime(deadline).strftime("%H:%M")
    for templates in (MANYCHAT_TEMPLATES, SMS_TEMPLATES, BODY_TEMPLATES):
        body = render_message("stock.arrived", context, templates)
        assert product.name in body
        assert f"Confirme ate as {local_deadline}" in body
        assert "https://shop.example/cart" in body
        assert "{" not in body, f"placeholder sem valor no corpo: {body}"
        assert "Notificacao:" not in body

    subject = SUBJECT_TEMPLATES["stock.arrived"].format(**context)
    assert product.name in subject


@pytest.mark.django_db
def test_stock_arrived_template_also_renders_for_stock_alert_subscribers():
    """O "Me avise" (sem reserva/prazo) compartilha o template: os placeholders
    reserve_note/deadline_note chegam vazios e o CTA aponta para o produto."""
    from shopman.shop.adapters._notification_templates import render_message
    from shopman.shop.adapters.notification_manychat import MESSAGE_TEMPLATES

    context = {
        "sku": "PAO-001",
        "product_name": "Pão rústico",
        "product_url": "https://shop.example/produto/PAO-001",
        "reserve_note": "",
        "deadline_note": "",
        "cta": "Garanta o seu:",
        "action_url": "https://shop.example/produto/PAO-001",
    }

    body = render_message("stock.arrived", context, MESSAGE_TEMPLATES)

    assert body == (
        "Boa noticia! Pão rústico chegou. Garanta o seu: "
        "https://shop.example/produto/PAO-001"
    )
