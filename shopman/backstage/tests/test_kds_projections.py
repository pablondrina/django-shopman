from __future__ import annotations

from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

import pytest

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.backstage.projections.kds import build_kds_board, build_kds_index, build_kds_ticket
from shopman.orderman.models import Order, OrderItem
from shopman.shop.models import Shop


@pytest.fixture
def kds_setup(db):
    Shop.objects.create(name="Loja")
    prep = KDSInstance.objects.create(ref="prep-proj", name="Preparo", type="prep", target_time_minutes=10)
    expedition = KDSInstance.objects.create(ref="exp-proj", name="Expedição", type="expedition")
    order = Order.objects.create(ref="KDS-PROJ-1", channel_ref="web", status="confirmed", total_q=1500, data={"customer": {"name": "Ana"}})
    OrderItem.objects.create(order=order, line_id="1", sku="SKU", name="Produto", qty=1, unit_price_q=1500, line_total_q=1500)
    ticket = KDSTicket.objects.create(
        order=order,
        kds_instance=prep,
        items=[{"sku": "SKU", "name": "Produto", "qty": 1, "notes": "Sem sal", "checked": False}],
    )
    ready = Order.objects.create(ref="KDS-READY", channel_ref="web", status="ready", total_q=2000, data={"fulfillment_type": "delivery"})
    OrderItem.objects.create(order=ready, line_id="2", sku="SKU2", name="Produto 2", qty=2, unit_price_q=1000, line_total_q=2000)
    return prep, expedition, ticket, ready


@pytest.mark.django_db
def test_build_kds_index_counts_prep_and_expedition(kds_setup):
    index = {item.ref: item for item in build_kds_index()}

    assert index["prep-proj"].pending_count == 1
    assert index["exp-proj"].pending_count == 1


@pytest.mark.django_db
def test_build_kds_board_returns_ticket_projection(kds_setup):
    prep, _, ticket, _ = kds_setup

    board = build_kds_board(prep.ref)

    assert board.instance_ref == prep.ref
    assert board.counts["pending"] == 1
    assert board.tickets[0].order_ref == "KDS-PROJ-1"
    assert board.tickets[0].items[0].notes == "Sem sal"


@pytest.mark.django_db
def test_build_kds_ticket_reflects_checked_state(kds_setup):
    _, _, ticket, _ = kds_setup
    ticket.items = [{"sku": "SKU", "name": "Produto", "qty": 1, "checked": True}]
    ticket.save(update_fields=["items"])

    projection = build_kds_ticket(ticket.pk)

    assert projection.all_checked is True
    assert projection.items[0].checked is True


@pytest.mark.django_db
def test_build_expedition_board_uses_ready_orders(kds_setup):
    _, expedition, _, ready = kds_setup

    board = build_kds_board(expedition.ref)

    assert board.is_expedition is True
    assert board.tickets[0].ref == ready.ref
    assert board.tickets[0].is_delivery is True


@pytest.mark.django_db
def test_kds_views_render_index_display_and_partial(client, kds_setup):
    prep, _, _, _ = kds_setup
    user = User.objects.create_user("kds-view", password="pw", is_staff=True)
    permission = Permission.objects.get(
        content_type=ContentType.objects.get_for_model(KDSTicket),
        codename="operate_kds",
    )
    user.user_permissions.add(permission)
    client.force_login(user)

    assert client.get(reverse("backstage:kds_index")).status_code == 200
    assert client.get(reverse("backstage:kds_display", args=[prep.ref])).status_code == 200
    partial = client.get(reverse("backstage:kds_ticket_list", args=[prep.ref]))
    assert partial.status_code == 200
    assert b"KDS-PROJ-1" in partial.content
