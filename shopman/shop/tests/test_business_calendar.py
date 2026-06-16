from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from shopman.shop.models import Shop
from shopman.shop.services.business_calendar import (
    available_dates,
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


def test_before_open_message_uses_plain_sentence():
    tz = ZoneInfo("America/Sao_Paulo")
    Shop.objects.create(
        name="Manha",
        timezone="America/Sao_Paulo",
        opening_hours=OPEN_MONDAY_TO_SATURDAY,
    )

    state = current_business_state(now=datetime(2026, 5, 4, 8, 0, tzinfo=tz))

    assert state.is_closed is True
    assert state.message == "Fechado. Abrimos às 9h"


def test_available_dates_drops_today_after_closing():
    """Depois do expediente, 'hoje' não é mais data fulfillável (eixo de HORA).

    Regressão: loja fechada às 18h ainda ofertava retirada/entrega para hoje.
    """
    tz = ZoneInfo("America/Sao_Paulo")
    shop = Shop.objects.create(
        name="Padaria",
        timezone="America/Sao_Paulo",
        opening_hours=OPEN_MONDAY_TO_SATURDAY,
    )
    monday = datetime(2026, 5, 4, 12, 0, tzinfo=tz)  # aberto (09–18)
    after_close = datetime(2026, 5, 4, 18, 30, tzinfo=tz)  # já fechou

    open_dates = available_dates(max_count=3, now=monday, shop=shop)
    closed_dates = available_dates(max_count=3, now=after_close, shop=shop)

    assert open_dates[0] == monday.date()  # aberto → hoje conta
    assert closed_dates[0] != after_close.date()  # fechou → hoje some
    assert closed_dates[0] == monday.date() + timedelta(days=1)  # vai p/ terça


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
