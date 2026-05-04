"""Operational calendar helpers for customer-facing promises and automation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone

logger = logging.getLogger(__name__)

DAY_NAMES_PT = {
    "monday": "segunda",
    "tuesday": "terça",
    "wednesday": "quarta",
    "thursday": "quinta",
    "friday": "sexta",
    "saturday": "sábado",
    "sunday": "domingo",
}
DAY_ORDER = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@dataclass(frozen=True)
class BusinessCalendarState:
    """Resolved operational state for one instant."""

    is_open: bool
    opens_at: str | None
    closes_at: str | None
    message: str
    next_open_at: datetime | None = None
    closed_reason: str = ""
    closure_source: str = ""
    resolved_at: datetime | None = None

    @property
    def is_closed(self) -> bool:
        return not self.is_open


def current_business_state(*, now: datetime | None = None, shop=None) -> BusinessCalendarState:
    """Return whether the shop is operational at ``now`` and when it opens next.

    The model is intentionally simple and canonical:
    regular weekly hours are stored in ``Shop.opening_hours``; closures such as
    holidays and collective vacations are date exceptions in
    ``Shop.defaults["closed_dates"]``.
    """
    shop = _load_shop(shop)
    if not shop:
        return BusinessCalendarState(is_open=True, opens_at=None, closes_at=None, message="")

    local_now = _localtime_for_shop(now or timezone.now(), shop)
    closed, closed_label, closure_source = closed_date_for(local_now.date(), _closed_dates(shop))
    day_window = _day_window(shop, local_now.date())
    next_open_at = _next_open_at(shop, local_now=local_now)

    if closed:
        message = f"Fechado hoje: {closed_label}" if closed_label else "Fechado hoje"
        return BusinessCalendarState(
            is_open=False,
            opens_at=None,
            closes_at=None,
            message=message,
            next_open_at=next_open_at,
            closed_reason=closed_label,
            closure_source=closure_source,
            resolved_at=local_now,
        )

    if day_window is None:
        if not _has_regular_hours(shop):
            return BusinessCalendarState(is_open=True, opens_at=None, closes_at=None, message="", resolved_at=local_now)
        return BusinessCalendarState(
            is_open=False,
            opens_at=None,
            closes_at=None,
            message="Fechado hoje",
            next_open_at=next_open_at,
            closure_source="weekly",
            resolved_at=local_now,
        )

    opens_at, closes_at = day_window
    current_time = local_now.time()
    if opens_at <= current_time < closes_at:
        return BusinessCalendarState(
            is_open=True,
            opens_at=_fmt_hhmm(opens_at),
            closes_at=_fmt_hhmm(closes_at),
            message=f"Aberto até {_fmt_hour(closes_at)}",
            next_open_at=None,
            resolved_at=local_now,
        )

    if current_time < opens_at:
        open_dt = datetime.combine(local_now.date(), opens_at, tzinfo=local_now.tzinfo)
        return BusinessCalendarState(
            is_open=False,
            opens_at=_fmt_hhmm(opens_at),
            closes_at=_fmt_hhmm(closes_at),
            message=f"Fechado — abrimos às {_fmt_hour(opens_at)}",
            next_open_at=open_dt,
            closure_source="before_open",
            resolved_at=local_now,
        )

    return BusinessCalendarState(
        is_open=False,
        opens_at=_fmt_hhmm(opens_at),
        closes_at=_fmt_hhmm(closes_at),
        message="Fechado",
        next_open_at=next_open_at,
        closure_source="after_close",
        resolved_at=local_now,
    )


def next_operational_deadline(
    *,
    timeout: timedelta,
    now: datetime | None = None,
    shop=None,
) -> tuple[datetime | None, BusinessCalendarState]:
    """Return the truthful deadline for an operator timeout.

    When the shop is closed, the timeout starts at the next known opening. If
    there is no configured future opening, no automated deadline is returned.
    """
    local_now = now or timezone.now()
    state = current_business_state(now=local_now, shop=shop)
    if state.is_open:
        return local_now + timeout, state
    if state.next_open_at:
        return state.next_open_at + timeout, state
    return None, state


def closed_date_for(day: date, closed_dates: list | tuple | None) -> tuple[bool, str, str]:
    """Return whether ``day`` is covered by a closure exception."""
    for entry in closed_dates or []:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label") or "").strip()
        if entry.get("closed") is False:
            continue
        if "date" in entry:
            try:
                if day == date.fromisoformat(str(entry["date"])):
                    return True, label, "date"
            except ValueError:
                continue
        if "from" in entry and "to" in entry:
            try:
                starts = date.fromisoformat(str(entry["from"]))
                ends = date.fromisoformat(str(entry["to"]))
            except ValueError:
                continue
            if starts <= day <= ends:
                return True, label, "range"
    return False, "", ""


def format_next_opening(value: datetime | None, *, now: datetime | None = None) -> str:
    """Format a next-opening datetime for compact customer copy."""
    if not value:
        return ""
    tz = value.tzinfo or timezone.get_current_timezone()
    local = timezone.localtime(value, timezone=tz)
    reference = now or timezone.now()
    if not timezone.is_aware(reference):
        reference = timezone.make_aware(reference, timezone=tz)
    today = timezone.localtime(reference, timezone=tz).date()
    tomorrow = today + timedelta(days=1)
    hour = _fmt_hour(local.time())
    if local.date() == today:
        return f"hoje às {hour}"
    if local.date() == tomorrow:
        return f"amanhã às {hour}"
    weekday = DAY_NAMES_PT.get(local.strftime("%A").lower(), local.strftime("%A").lower())
    return f"{weekday} às {hour}"


def _load_shop(shop):
    if shop is not None:
        return shop
    try:
        from shopman.shop.models import Shop

        return Shop.load()
    except Exception:
        logger.debug("business_calendar.load_shop_failed", exc_info=True)
        return None


def _localtime_for_shop(value: datetime, shop) -> datetime:
    if not timezone.is_aware(value):
        value = timezone.make_aware(value)
    tz_name = getattr(shop, "timezone", "") or timezone.get_current_timezone_name()
    if not isinstance(tz_name, str):
        tz_name = timezone.get_current_timezone_name()
    try:
        tz = ZoneInfo(tz_name)
    except (ValueError, ZoneInfoNotFoundError):
        tz = timezone.get_current_timezone()
    return timezone.localtime(value, timezone=tz)


def _closed_dates(shop) -> list:
    defaults = getattr(shop, "defaults", None) or {}
    if not isinstance(defaults, dict):
        return []
    calendar = defaults.get("calendar") if isinstance(defaults.get("calendar"), dict) else {}
    dates = []
    for key in ("closed_dates", "closures", "holidays"):
        value = defaults.get(key)
        if isinstance(value, list):
            dates.extend(value)
    for key in ("closed_dates", "closures", "holidays"):
        value = calendar.get(key)
        if isinstance(value, list):
            dates.extend(value)
    return dates


def _has_regular_hours(shop) -> bool:
    hours = getattr(shop, "opening_hours", None)
    return isinstance(hours, dict) and any(
        isinstance(value, dict) and value.get("open") and value.get("close")
        for value in hours.values()
    )


def _day_window(shop, day: date) -> tuple[time, time] | None:
    hours = getattr(shop, "opening_hours", None)
    if not isinstance(hours, dict) or not hours:
        return None
    weekday = DAY_ORDER[day.weekday()]
    raw = hours.get(weekday)
    if not isinstance(raw, dict):
        return None
    try:
        opens_at = time.fromisoformat(str(raw["open"]))
        closes_at = time.fromisoformat(str(raw["close"]))
    except (KeyError, TypeError, ValueError):
        return None
    if opens_at >= closes_at:
        return None
    return opens_at, closes_at


def _next_open_at(shop, *, local_now: datetime) -> datetime | None:
    if not _has_regular_hours(shop):
        return None
    for offset in range(0, 15):
        candidate_date = local_now.date() + timedelta(days=offset)
        closed, _, _ = closed_date_for(candidate_date, _closed_dates(shop))
        if closed:
            continue
        window = _day_window(shop, candidate_date)
        if window is None:
            continue
        opens_at, closes_at = window
        candidate = datetime.combine(candidate_date, opens_at, tzinfo=local_now.tzinfo)
        if candidate <= local_now:
            if local_now.date() == candidate_date and local_now.time() < closes_at:
                return candidate
            continue
        return candidate
    return None


def _fmt_hhmm(value: time) -> str:
    return value.strftime("%H:%M")


def _fmt_hour(value: time) -> str:
    if value.minute:
        return f"{value.hour}h{value.minute:02d}"
    return f"{value.hour}h"
