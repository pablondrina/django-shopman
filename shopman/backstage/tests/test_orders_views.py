from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import NoReverseMatch, reverse
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.models import OperatorAlert
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

    main = client.get(reverse("admin_console_orders"))
    listing = client.get(reverse("admin_console_orders_list"))
    detail = client.get(reverse("admin_console_order_detail", args=[order.ref]))
    history = client.get(reverse("admin:orderman_order_changelist"))

    assert main.status_code == 200
    assert listing.status_code == 200
    assert detail.status_code == 200
    assert history.status_code in {200, 302}
    assert b"Produto" in detail.content


@pytest.mark.django_db
def test_order_detail_renders_timeline_events(client, orders_user, order):
    order.emit_event(
        event_type="status_changed",
        actor="operator:ana",
        payload={"old_status": "new", "new_status": "confirmed"},
    )
    client.force_login(orders_user)

    response = client.get(reverse("admin_console_order_detail", args=[order.ref]))

    assert response.status_code == 200
    body = response.content.decode()
    assert "operator:ana" in body
    assert "Confirmado" in body


@pytest.mark.django_db
def test_orders_board_uses_sse_without_aggressive_polling(client, orders_user, order):
    client.force_login(orders_user)

    response = client.get(reverse("admin_console_orders"))

    assert response.status_code == 200
    body = response.content.decode()
    assert 'hx-trigger="sse:backstage-orders-update, ped-board-refresh from:body, every 30s"' in body
    assert 'sse:backstage-orders-update, every 5s' not in body
    assert "/admin/operacao/pedidos/lista/" in body


@pytest.mark.django_db
def test_order_action_triggers_board_refresh(client, orders_user, order):
    client.force_login(orders_user)

    response = client.post(reverse("admin_console_order_advance", args=[order.ref]))

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("admin_console_orders")


@pytest.mark.django_db
def test_order_notes_view_persists_internal_notes(client, orders_user, order):
    client.force_login(orders_user)

    response = client.post(reverse("admin_console_order_detail", args=[order.ref]), {"notes": "Separar"})

    assert response.status_code == 302
    order.refresh_from_db()
    assert order.data["internal_notes"] == "Separar"


@pytest.mark.django_db
def test_order_reject_requires_reason(client, orders_user, order):
    client.force_login(orders_user)

    response = client.post(reverse("admin_console_order_reject", args=[order.ref]), {"reason": ""})

    assert response.status_code == 200


@pytest.mark.django_db
def test_alert_acknowledge_view_marks_alert(client, orders_user):
    client.force_login(orders_user)
    alert = OperatorAlert.objects.create(type="stock_low", severity="warning", message="Baixo")

    response = client.post(reverse("backstage:alert_ack", args=[alert.pk]))

    assert response.status_code == 200
    alert.refresh_from_db()
    assert alert.acknowledged is True


@pytest.mark.django_db
def test_old_orders_route_names_are_not_registered():
    for name in (
        "backstage:gestor_pedidos",
        "backstage:gestor_list_partial",
        "backstage:gestor_detail",
        "backstage:gestor_confirm",
        "backstage:gestor_reject",
        "backstage:gestor_advance",
        "backstage:gestor_notes",
        "backstage:gestor_historico",
    ):
        with pytest.raises(NoReverseMatch):
            reverse(name, args=["ORD-X"] if name not in {"backstage:gestor_pedidos", "backstage:gestor_list_partial", "backstage:gestor_historico"} else [])
