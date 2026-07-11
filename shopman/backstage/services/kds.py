"""Backstage KDS mutation facade."""

from __future__ import annotations

from shopman.backstage.services.exceptions import KDSError
from shopman.shop.services import kds as kds_core


def check_ticket_item(*, ticket_pk: int, index: int, actor: str):
    from shopman.backstage.models import KDSTicket

    ticket = KDSTicket.objects.filter(pk=ticket_pk).first()
    if ticket is None:
        raise KDSError("Ticket não encontrado.")
    if not kds_core.toggle_ticket_item(ticket, index=index, actor=actor):
        raise KDSError("Ticket não está aberto.")
    return ticket


def set_ticket_item_checked(*, ticket_pk: int, index: int, checked: bool, actor: str):
    from shopman.backstage.models import KDSTicket

    ticket = KDSTicket.objects.filter(pk=ticket_pk).first()
    if ticket is None:
        raise KDSError("Ticket não encontrado.")
    if not 0 <= index < len(ticket.items):
        raise KDSError("Item não encontrado.")

    current = bool(ticket.items[index].get("checked", False))
    if current != checked:
        if not kds_core.toggle_ticket_item(ticket, index=index, actor=actor):
            raise KDSError("Ticket não está aberto.")
        ticket.refresh_from_db()
    return ticket


def mark_ticket_done(*, ticket_pk: int, actor: str):
    from shopman.backstage.models import KDSTicket

    ticket = KDSTicket.objects.filter(pk=ticket_pk).first()
    if ticket is None:
        raise KDSError("Ticket não encontrado.")
    if ticket.status == "done":
        # Replay (duas estações bumpando o mesmo ticket) = sucesso no-op,
        # mesma semântica de expedition_action_idempotent.
        return ticket
    if not kds_core.complete_ticket(ticket, actor=actor):
        raise KDSError("Ticket não está aberto.")
    return ticket


def recall_ticket(*, ticket_pk: int, actor: str):
    from shopman.backstage.models import KDSTicket

    ticket = KDSTicket.objects.filter(pk=ticket_pk).first()
    if ticket is None:
        raise KDSError("Ticket não encontrado.")
    if not kds_core.reopen_ticket(ticket, actor=actor):
        raise KDSError("Ticket não está concluído.")
    return ticket


def acknowledge_ticket(*, ticket_pk: int, actor: str):
    from shopman.backstage.models import KDSTicket

    ticket = KDSTicket.objects.filter(pk=ticket_pk).first()
    if ticket is None:
        raise KDSError("Ticket não encontrado.")
    if not kds_core.acknowledge_ticket(ticket, actor=actor):
        raise KDSError("Ticket não está cancelado.")
    return ticket


def expedition_action(*, order_id: int, action: str, actor: str):
    try:
        return kds_core.expedition_action_by_order_id(order_id, action=action, actor=actor)
    except ValueError as exc:
        raise KDSError("Ação inválida") from exc


def expedition_action_idempotent(*, order_id: int, action: str, actor: str):
    from shopman.orderman.models import Order

    order = Order.objects.filter(pk=order_id).first()
    if order is None:
        raise KDSError("Pedido não encontrado.")
    if action == "dispatch" and order.status == Order.Status.DISPATCHED:
        return order.status
    if action == "complete" and order.status == Order.Status.COMPLETED:
        return order.status
    return expedition_action(order_id=order_id, action=action, actor=actor)
