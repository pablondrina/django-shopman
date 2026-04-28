"""Alert adapter — wraps OperatorAlert creation/query with lazy imports.

Keeps shop/ free of direct shopman.backstage imports.
"""
from __future__ import annotations

from typing import Any


def create(type: str, severity: str, message: str, *, order_ref: str = "") -> Any:
    """Create an OperatorAlert. Returns the created instance."""
    from shopman.backstage.models import OperatorAlert

    return OperatorAlert.objects.create(
        type=type,
        severity=severity,
        message=message,
        order_ref=order_ref,
    )


def recent_exists(type: str, since, *, message_contains: str | None = None) -> bool:
    """Return True if an alert of this type was created at or after `since`.

    Used for debouncing: skip duplicate alerts within a time window.
    """
    from shopman.backstage.models import OperatorAlert

    qs = OperatorAlert.objects.filter(type=type, created_at__gte=since)
    if message_contains is not None:
        qs = qs.filter(message__contains=message_contains)
    return qs.exists()


def connect_saved(receiver, *, dispatch_uid: str, weak: bool = False) -> None:
    """Connect a receiver to OperatorAlert post-save without leaking imports."""
    from django.db.models.signals import post_save
    from shopman.backstage.models import OperatorAlert

    post_save.connect(
        receiver,
        sender=OperatorAlert,
        dispatch_uid=dispatch_uid,
        weak=weak,
    )
