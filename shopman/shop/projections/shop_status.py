"""Business-calendar reads exposed to surfaces (read-side facade).

``current_business_state`` and ``format_next_opening`` live in the spine module
``shop/services/business_calendar`` (shared with lifecycle, rules and
omotenashi). Surfaces import them through this read-side facade so the
presentation never reaches into ``shop.services`` (ADR-014 rule R-A).

Delegation is by module reference so existing patch targets on
``shop.services.business_calendar`` continue to apply.
"""

from __future__ import annotations

from datetime import datetime

from shopman.shop.services import business_calendar


def business_state(*, now: datetime | None = None, shop=None):
    """Current open/closed business-calendar state (data)."""
    return business_calendar.current_business_state(now=now, shop=shop)


def next_opening_phrase(value: datetime | None, *, now: datetime | None = None) -> str:
    """Bridge to the next-opening phrase the surface renders."""
    return business_calendar.format_next_opening(value, now=now)


__all__ = ["business_state", "next_opening_phrase"]
