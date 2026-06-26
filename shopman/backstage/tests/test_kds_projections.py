from __future__ import annotations

import pytest
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.backstage.projections.kds import build_kds_board, build_kds_index, build_kds_ticket
from shopman.shop.models import Shop


@pytest.fixture
def kds_setup(db):
    Shop.objects.create(name="Loja")
    prep = KDSInstance.objects.create(ref="prep-proj", name="Preparo", type="prep", target_time_minutes=10)
    expedition = KDSInstance.objects.create(ref="exp-proj", name="Expedição", type="expedition")
    order = Order.objects.create(ref="KDS-PROJ-1", channel_ref="web", session_key="sk-kds-proj-1", status="confirmed", total_q=1500, data={"customer": {"name": "Ana"}})
    OrderItem.objects.create(order=order, line_id="1", sku="SKU", name="Produto", qty=1, unit_price_q=1500, line_total_q=1500)
    ticket = KDSTicket.objects.create(
        session_key=order.session_key,
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
def test_build_kds_board_exposes_recent_cancelled_tickets(kds_setup):
    prep, _, ticket, _ = kds_setup
    ticket.status = "cancelled"
    ticket.cancelled_at = timezone.now()
    ticket.save(update_fields=["status", "cancelled_at"])

    board = build_kds_board(prep.ref)

    assert board.counts["total"] == 0
    assert board.counts["cancelled_recent"] == 1
    assert board.cancelled_tickets[0].order_ref == "KDS-PROJ-1"
    assert board.cancelled_tickets[0].status_label == "Cancelado"


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
    assert board.tickets[0].order_ref == ready.ref
    assert board.tickets[0].is_delivery is True
    assert board.tickets[0].units_count == "2"
    assert board.tickets[0].line_count == 1


# A renderização das telas KDS migrou p/ o app Nuxt (kds.) sobre a API headless
# (api/v1/backstage/kds/*, ver test_api_kds_surface.py); as views HTMX foram removidas.


def test_old_admin_console_kds_routes_are_not_registered():
    for name in (
        "admin_console_kds",
        "admin_console_kds_display",
        "admin_console_kds_tickets",
        "admin_console_kds_ticket_check",
        "admin_console_kds_ticket_done",
        "admin_console_kds_expedition_action",
    ):
        with pytest.raises(NoReverseMatch):
            reverse(name, args=["prep"] if "display" in name or "tickets" in name else [1] if name != "admin_console_kds" else [])
