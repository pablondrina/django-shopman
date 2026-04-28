"""Backstage KDS command facade."""

from __future__ import annotations

from shopman.backstage.services.exceptions import KDSError
from shopman.shop.services import kds as kds_core


def check_ticket_item(*, ticket_pk: int, index: int, actor: str):
    from shopman.backstage.models import KDSTicket

    ticket = KDSTicket.objects.filter(pk=ticket_pk).first()
    if ticket is None:
        raise KDSError("Ticket não encontrado.")
    kds_core.toggle_ticket_item(ticket, index=index, actor=actor)
    return ticket


def mark_ticket_done(*, ticket_pk: int, actor: str):
    from shopman.backstage.models import KDSTicket

    ticket = KDSTicket.objects.filter(pk=ticket_pk).first()
    if ticket is None:
        raise KDSError("Ticket não encontrado.")
    kds_core.complete_ticket(ticket, actor=actor)
    return ticket


def expedition_action(*, order_id: int, action: str, actor: str):
    try:
        return kds_core.expedition_action_by_order_id(order_id, action=action, actor=actor)
    except ValueError as exc:
        raise KDSError("Ação inválida") from exc
