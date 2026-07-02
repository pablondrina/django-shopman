"""KDS adapter — wraps KDSInstance/KDSTicket CRUD with lazy imports.

Keeps shop/ free of direct shopman.backstage imports.
"""
from __future__ import annotations

from typing import Any


def get_active_prep_instances() -> list[Any]:
    """Active KDS instances excluding expedition (prep + picking stations)."""
    from shopman.backstage.models import KDSInstance

    return list(
        KDSInstance.objects.filter(is_active=True)
        .exclude(type="expedition")
        .prefetch_related("collections")
    )


def ticket_exists_for_order(order) -> bool:
    from shopman.backstage.models import KDSTicket

    return KDSTicket.objects.filter(session_key=order.session_key).exists()


def fired_line_ids_for_session(session_key: str) -> set[str]:
    """Line ids already on a live (non-cancelled) ticket for this session_key.

    The durable fire-ledger: survives commit (tickets are keyed by session_key,
    not the Order). A cancelled line is absent — so it may re-fire (reprint).
    """
    from shopman.backstage.models import KDSTicket

    fired: set[str] = set()
    rows = (
        KDSTicket.objects.filter(session_key=session_key)
        .exclude(status="cancelled")
        .values_list("items", flat=True)
    )
    for items in rows:
        for item in items or []:
            line_id = item.get("line_id")
            if line_id:
                fired.add(line_id)
    return fired


def create_ticket(session_key: str, kds_instance, items: list) -> Any:
    from shopman.backstage.models import KDSTicket

    return KDSTicket.objects.create(
        session_key=session_key, kds_instance=kds_instance, items=items,
    )


def unfire_session_lines(session_key: str, line_ids: list[str]) -> dict:
    """Un-fire specific lines for a session: remove them from their live tickets.

    A ticket loses only the targeted line items; when that empties the ticket it
    is cancelled (status="cancelled"), otherwise the surviving courses keep their
    prep progress. The model save re-emits the KDS SSE event either way. Removing
    a line drops it from the fire-ledger, so it may be fired again (reprint =
    un-fire + fire). Returns ``{"cancelled": n, "trimmed": n}``.
    """
    from django.utils import timezone

    from shopman.backstage.models import KDSTicket

    targets = {str(lid) for lid in (line_ids or []) if str(lid)}
    cancelled = trimmed = 0
    if not targets:
        return {"cancelled": 0, "trimmed": 0}

    tickets = KDSTicket.objects.filter(session_key=session_key).exclude(status="cancelled")
    for ticket in tickets:
        items = ticket.items or []
        kept = [it for it in items if it.get("line_id") not in targets]
        if len(kept) == len(items):
            continue
        if kept:
            ticket.items = kept
            ticket.save(update_fields=["items"])
            trimmed += 1
        else:
            ticket.status = "cancelled"
            ticket.cancelled_at = timezone.now()
            ticket.save(update_fields=["status", "cancelled_at"])
            cancelled += 1
    return {"cancelled": cancelled, "trimmed": trimmed}


def cancel_open_tickets(order) -> int:
    """Cancel all open tickets for order. Returns count cancelled."""
    return cancel_open_tickets_for_session(order.session_key)


def cancel_open_tickets_for_session(session_key: str) -> int:
    """Cancel all open tickets for a session (comanda descartada sem venda)."""
    from django.utils import timezone

    from shopman.backstage.models import KDSTicket

    tickets = list(KDSTicket.objects.filter(
        session_key=session_key, status__in=["pending", "in_progress"]
    ))
    cancelled_at = timezone.now()
    for ticket in tickets:
        ticket.status = "cancelled"
        ticket.cancelled_at = cancelled_at
        ticket.save(update_fields=["status", "cancelled_at"])
    return len(tickets)


def get_tickets(order):
    from shopman.backstage.models import KDSTicket

    return KDSTicket.objects.filter(session_key=order.session_key)


def get_completed_ticket_timestamps(order) -> list[tuple[int, Any]]:
    """Return [(pk, completed_at)] for tickets with a completed_at timestamp."""
    from shopman.backstage.models import KDSTicket

    return list(
        KDSTicket.objects.filter(session_key=order.session_key, completed_at__isnull=False)
        .values_list("pk", "completed_at")
    )


def shift_ticket_completed_at(pk: int, completed_at) -> None:
    from shopman.backstage.models import KDSTicket

    KDSTicket.objects.filter(pk=pk).update(completed_at=completed_at)


def get_ticket_model():
    """Return KDSTicket model for signal wiring without direct surface imports."""
    from shopman.backstage.models import KDSTicket

    return KDSTicket


def active_ticket_count(kds_instance_id) -> int:
    from shopman.backstage.models import KDSTicket

    return KDSTicket.objects.filter(
        kds_instance_id=kds_instance_id,
        status__in=["pending", "in_progress"],
    ).count()
