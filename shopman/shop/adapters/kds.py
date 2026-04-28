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

    return KDSTicket.objects.filter(order=order).exists()


def create_ticket(order, kds_instance, items: list) -> Any:
    from shopman.backstage.models import KDSTicket

    return KDSTicket.objects.create(order=order, kds_instance=kds_instance, items=items)


def cancel_open_tickets(order) -> int:
    """Cancel all open tickets for order. Returns count cancelled."""
    from shopman.backstage.models import KDSTicket

    return KDSTicket.objects.filter(
        order=order, status__in=["pending", "in_progress"]
    ).update(status="cancelled")


def get_tickets(order):
    from shopman.backstage.models import KDSTicket

    return KDSTicket.objects.filter(order=order)


def get_completed_ticket_timestamps(order) -> list[tuple[int, Any]]:
    """Return [(pk, completed_at)] for tickets with a completed_at timestamp."""
    from shopman.backstage.models import KDSTicket

    return list(
        KDSTicket.objects.filter(order=order, completed_at__isnull=False)
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
