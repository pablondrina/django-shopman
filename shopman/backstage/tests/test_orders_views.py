from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from shopman.backstage.models import OperatorAlert
from shopman.orderman.models import Order, OrderItem
from shopman.shop.models import Shop


@pytest.fixture
def orders_user(db):
    Shop.objects.create(name="Loja")
    user = User.objects.create_user("orders-view", password="pw", is_staff=True)
    permission = Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"),
        codename="manage_orders",
    )
    user.user_permissions.add(permission)
    return user


@pytest.fixture
def order(db):
    order = Order.objects.create(
        ref="ORD-VIEW-1",
        channel_ref="web",
        status="confirmed",
        total_q=1500,
        data={"customer": {"name": "Ana"}, "payment": {"method": "cash"}},
    )
    OrderItem.objects.create(order=order, line_id="1", sku="SKU", name="Produto", qty=1, unit_price_q=1500, line_total_q=1500)
    return order


@pytest.mark.django_db
def test_orders_main_list_detail_and_history_views(client, orders_user, order):
    client.force_login(orders_user)

    main = client.get(reverse("backstage:gestor_pedidos"))
    listing = client.get(reverse("backstage:gestor_list_partial"))
    detail = client.get(reverse("backstage:gestor_detail", args=[order.ref]))
    history = client.get(reverse("backstage:gestor_historico"))

    assert main.status_code == 200
    assert listing.status_code == 200
    assert detail.status_code == 200
    assert history.status_code == 200
    assert b"Produto" in detail.content


@pytest.mark.django_db
def test_order_notes_view_persists_internal_notes(client, orders_user, order):
    client.force_login(orders_user)

    response = client.post(reverse("backstage:gestor_notes", args=[order.ref]), {"notes": "Separar"})

    assert response.status_code == 200
    order.refresh_from_db()
    assert order.data["internal_notes"] == "Separar"


@pytest.mark.django_db
def test_order_reject_requires_reason(client, orders_user, order):
    client.force_login(orders_user)

    response = client.post(reverse("backstage:gestor_reject", args=[order.ref]), {"reason": ""})

    assert response.status_code == 422


@pytest.mark.django_db
def test_alert_acknowledge_view_marks_alert(client, orders_user):
    client.force_login(orders_user)
    alert = OperatorAlert.objects.create(type="stock_low", severity="warning", message="Baixo")

    response = client.post(reverse("backstage:gestor_alert_ack", args=[alert.pk]))

    assert response.status_code == 200
    alert.refresh_from_db()
    assert alert.acknowledged is True
