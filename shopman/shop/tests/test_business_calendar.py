from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from shopman.shop.models import Shop
from shopman.shop.services.business_calendar import (
    current_business_state,
    format_next_opening,
    next_operational_deadline,
)

pytestmark = pytest.mark.django_db


OPEN_MONDAY_TO_SATURDAY = {
    "monday": {"open": "09:00", "close": "18:00"},
    "tuesday": {"open": "09:00", "close": "18:00"},
    "wednesday": {"open": "09:00", "close": "18:00"},
    "thursday": {"open": "09:00", "close": "18:00"},
    "friday": {"open": "09:00", "close": "18:00"},
    "saturday": {"open": "09:00", "close": "18:00"},
}


def test_sunday_without_schedule_defers_to_monday_opening():
    tz = ZoneInfo("America/Sao_Paulo")
    Shop.objects.create(
        name="Calendario",
        timezone="America/Sao_Paulo",
        opening_hours=OPEN_MONDAY_TO_SATURDAY,
    )

    now = datetime(2026, 5, 3, 12, 0, tzinfo=tz)
    state = current_business_state(now=now)

    assert state.is_closed is True
    assert state.message == "Fechado hoje"
    assert state.next_open_at == datetime(2026, 5, 4, 9, 0, tzinfo=tz)
    assert format_next_opening(state.next_open_at, now=state.resolved_at) == "amanhã às 9h"


def test_closure_range_skips_collective_vacation():
    tz = ZoneInfo("America/Sao_Paulo")
    Shop.objects.create(
        name="Ferias",
        timezone="America/Sao_Paulo",
        opening_hours=OPEN_MONDAY_TO_SATURDAY,
        defaults={
            "closed_dates": [
                {"from": "2026-05-04", "to": "2026-05-06", "label": "Férias coletivas"}
            ]
        },
    )

    now = datetime(2026, 5, 4, 10, 0, tzinfo=tz)
    state = current_business_state(now=now)

    assert state.is_closed is True
    assert state.closed_reason == "Férias coletivas"
    assert state.next_open_at == datetime(2026, 5, 7, 9, 0, tzinfo=tz)
    assert format_next_opening(state.next_open_at, now=state.resolved_at) == "quinta às 9h"


def test_operational_deadline_starts_at_next_opening_when_closed():
    tz = ZoneInfo("America/Sao_Paulo")
    Shop.objects.create(
        name="Timer",
        timezone="America/Sao_Paulo",
        opening_hours=OPEN_MONDAY_TO_SATURDAY,
    )

    deadline, state = next_operational_deadline(
        timeout=timedelta(minutes=5),
        now=datetime(2026, 5, 3, 12, 0, tzinfo=tz),
    )

    assert state.is_closed is True
    assert deadline == datetime(2026, 5, 4, 9, 5, tzinfo=tz)
