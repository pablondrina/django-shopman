from __future__ import annotations

DAY_NAMES_PT = {
    "monday": "Segunda",
    "tuesday": "Terça",
    "wednesday": "Quarta",
    "thursday": "Quinta",
    "friday": "Sexta",
    "saturday": "Sábado",
    "sunday": "Domingo",
}

DAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _shop_status() -> dict:
    """Return shop open/closed status based on Shop.opening_hours.

    Returns dict: {is_open, opens_at, closes_at, message}
    """
    from shopman.shop.services.business_calendar import current_business_state, format_next_opening

    state = current_business_state()
    message = state.message
    if state.is_closed and state.next_open_at:
        message = f"{message} — abrimos {format_next_opening(state.next_open_at, now=state.resolved_at)}"
    return {
        "is_open": state.is_open,
        "opens_at": state.opens_at,
        "closes_at": state.closes_at,
        "message": message,
    }


def _format_opening_hours() -> list[dict]:
    """Format Shop.opening_hours into display-ready lines for templates.

    Groups consecutive days with the same hours into ranges.
    Returns list of {label, hours} dicts, e.g.:
      [{"label": "Terça a Sábado", "hours": "7h — 19h"},
       {"label": "Domingo", "hours": "7h — 13h"},
       {"label": "Segunda", "hours": "Fechado"}]
    """
    from shopman.shop.models import Shop

    shop = Shop.load()
    if not shop or not shop.opening_hours:
        return []

    def _fmt_time(t: str) -> str:
        """'06:00' -> '6h', '20:00' -> '20h', '07:30' -> '7h30'."""
        parts = t.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        if m:
            return f"{h}h{m:02d}"
        return f"{h}h"

    # Build (day, hours_str) pairs in order
    day_hours: list[tuple[str, str]] = []
    for day in DAY_ORDER:
        info = shop.opening_hours.get(day)
        if info and info.get("open") and info.get("close"):
            day_hours.append((day, f"{_fmt_time(info['open'])} — {_fmt_time(info['close'])}"))
        else:
            day_hours.append((day, "Fechado"))

    # Group consecutive days with same hours
    groups: list[tuple[list[str], str]] = []
    for day, hours in day_hours:
        if groups and groups[-1][1] == hours:
            groups[-1][0].append(day)
        else:
            groups.append(([day], hours))

    result = []
    for days, hours in groups:
        if len(days) == 1:
            label = DAY_NAMES_PT[days[0]]
        elif len(days) == 2:
            label = f"{DAY_NAMES_PT[days[0]]} e {DAY_NAMES_PT[days[1]]}"
        else:
            label = f"{DAY_NAMES_PT[days[0]]} a {DAY_NAMES_PT[days[-1]]}"
        result.append({"label": label, "hours": hours})

    return result
