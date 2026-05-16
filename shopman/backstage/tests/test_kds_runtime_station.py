from __future__ import annotations

from pathlib import Path

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.models import KDSInstance, KDSTicket


@pytest.fixture
def kds_runtime_setup(db):
    prep = KDSInstance.objects.create(ref="prep-runtime", name="Preparo Runtime", type="prep", target_time_minutes=10)
    expedition = KDSInstance.objects.create(ref="exp-runtime", name="Expedição Runtime", type="expedition")
    order = Order.objects.create(
        ref="KDS-RUNTIME-1",
        channel_ref="web",
        status=Order.Status.CONFIRMED,
        total_q=1500,
        data={"customer": {"name": "Ana"}, "fulfillment_type": "pickup"},
    )
    OrderItem.objects.create(order=order, line_id="1", sku="SKU", name="Produto", qty=1, unit_price_q=1500, line_total_q=1500)
    ticket = KDSTicket.objects.create(
        order=order,
        kds_instance=prep,
        items=[{"sku": "SKU", "name": "Produto", "qty": 1, "notes": "Sem sal", "checked": False}],
    )
    ready = Order.objects.create(
        ref="KDS-READY-RUNTIME",
        channel_ref="web",
        status=Order.Status.READY,
        total_q=2000,
        data={"customer": {"name": "Bia"}, "fulfillment_type": "pickup"},
    )
    OrderItem.objects.create(order=ready, line_id="2", sku="SKU2", name="Produto 2", qty=2, unit_price_q=1000, line_total_q=2000)
    return prep, expedition, ticket, ready


def _kds_operator() -> User:
    user = User.objects.create_user("kds-runtime", password="pw", is_staff=True)
    permission = Permission.objects.get(
        content_type=ContentType.objects.get_for_model(KDSTicket),
        codename="operate_kds",
    )
    user.user_permissions.add(permission)
    return user


@pytest.mark.django_db
def test_kds_runtime_station_routes_render_for_operator(client, kds_runtime_setup):
    prep, expedition, _, _ = kds_runtime_setup
    client.force_login(_kds_operator())

    response = client.get(reverse("backstage:kds_station_runtime", args=[prep.ref]))
    cards = client.get(reverse("backstage:kds_station_runtime_cards", args=[prep.ref]))
    expedition_cards = client.get(reverse("backstage:kds_station_runtime_cards", args=[expedition.ref]))

    assert response.status_code == 200
    assert cards.status_code == 200
    assert expedition_cards.status_code == 200
    html = response.content.decode()
    assert "Preparo Runtime" in html
    assert "sse:backstage-kds-update" in html
    assert "every 15s" in html
    assert 'aria-live="polite"' in html
    assert "KDS-RUNTIME-1" in cards.content.decode()
    assert "KDS-READY-RUNTIME" in expedition_cards.content.decode()


@pytest.mark.django_db
def test_kds_runtime_station_requires_operate_permission(client, kds_runtime_setup):
    prep, _, _, _ = kds_runtime_setup
    user = User.objects.create_user("staff-readonly", password="pw", is_staff=True)
    client.force_login(user)

    response = client.get(reverse("backstage:kds_station_runtime", args=[prep.ref]))

    assert response.status_code == 403


@pytest.mark.django_db
def test_kds_runtime_item_check_is_idempotent(client, kds_runtime_setup):
    _, _, ticket, _ = kds_runtime_setup
    client.force_login(_kds_operator())
    url = reverse("backstage:kds_station_runtime_check", args=[ticket.pk])

    first = client.post(url, {"index": "0", "checked": "1"}, HTTP_HX_REQUEST="true")
    ticket.refresh_from_db()
    assert first.status_code == 200
    assert first.headers["HX-Trigger"] == "kdsStationChanged"
    assert ticket.items[0]["checked"] is True

    second = client.post(url, {"index": "0", "checked": "1"}, HTTP_HX_REQUEST="true")
    ticket.refresh_from_db()
    assert second.status_code == 200
    assert ticket.items[0]["checked"] is True


@pytest.mark.django_db
def test_kds_runtime_done_marks_ticket_done(client, kds_runtime_setup):
    _, _, ticket, _ = kds_runtime_setup
    client.force_login(_kds_operator())

    response = client.post(
        reverse("backstage:kds_station_runtime_done", args=[ticket.pk]),
        HTTP_HX_REQUEST="true",
    )
    ticket.refresh_from_db()

    assert response.status_code == 200
    assert ticket.status == "done"
    assert all(item["checked"] for item in ticket.items)


@pytest.mark.django_db
def test_kds_runtime_expedition_action_completes_pickup_order(client, kds_runtime_setup):
    _, expedition, _, ready = kds_runtime_setup
    client.force_login(_kds_operator())

    response = client.post(
        reverse("backstage:kds_station_runtime_expedition", args=[ready.pk]),
        {"station_ref": expedition.ref, "action": "complete"},
        HTTP_HX_REQUEST="true",
    )
    ready.refresh_from_db()

    assert response.status_code == 200
    assert ready.status == Order.Status.COMPLETED


def test_kds_runtime_station_template_uses_realtime_with_polling_fallback():
    source = Path("shopman/backstage/templates/runtime/kds_station/index.html").read_text()

    assert "hx-ext=\"sse\"" in source
    assert "sse-connect" in source
    assert "sse:backstage-kds-update" in source
    assert "every 15s" in source
    assert "kdsStationChanged from:body" in source
