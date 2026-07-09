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
    from shopman.shop.projections.shop_status import business_state, next_opening_phrase

    state = business_state()
    message = state.message or ""
    if state.is_closed and state.next_open_at:
        next_opening = next_opening_phrase(state.next_open_at, now=state.resolved_at)
        if next_opening and "abrimos" not in message.lower():
            message = f"{message}. Abrimos {next_opening}." if message else f"Abrimos {next_opening}."
    return {
        "is_open": state.is_open,
        "label": _status_label(state),
        "opens_at": state.opens_at,
        "closes_at": state.closes_at,
        "message": message,
    }


def _status_label(state) -> str:
    """Status badge label — copy owned by the omotenashi registry (``SHOP_STATUS_*``).

    Escapa o genérico fixo pelo conjunto granular do registro: aberto até
    {hora}, fecha em breve, fechado, abre às {hora}. Os prefixos vêm do
    registro (admin-configurável); a hora vem do estado do calendário. Só o
    fechamento antes de abrir carrega um horário de abertura útil — depois de
    fechar ou em feriado, ``opens_at`` não serve, então fica "Fechado" seco.
    """
    from shopman.shop.omotenashi import resolve_copy

    def _copy(key: str) -> str:
        return (resolve_copy(key, moment="*").message or "").strip()

    if state.is_open:
        closes = _human_time(state.closes_at)
        if not closes:
            return _copy("SHOP_STATUS_OPEN")
        prefix = "SHOP_STATUS_OPEN_CLOSING_SOON" if _closing_soon(state) else "SHOP_STATUS_OPEN_UNTIL"
        return f"{_copy(prefix)} {closes}".strip()

    if (
        state.opens_at
        and getattr(state, "closure_source", "") != "after_close"
        and not getattr(state, "closed_reason", "")
    ):
        opens = _human_time(state.opens_at)
        if opens:
            return f"{_copy('SHOP_STATUS_CLOSED_OPENS_AT')} {opens}".strip()
    return _copy("SHOP_STATUS_CLOSED")


def _closing_soon(state, *, threshold_min: int = 60) -> bool:
    """Whether the shop closes within ``threshold_min`` minutes of resolution."""
    resolved_at = getattr(state, "resolved_at", None)
    if not (state.closes_at and resolved_at):
        return False
    try:
        hour, minute = (int(part) for part in state.closes_at.split(":"))
    except (ValueError, AttributeError):
        return False
    close_dt = resolved_at.replace(hour=hour, minute=minute, second=0, microsecond=0)
    delta_min = (close_dt - resolved_at).total_seconds() / 60
    return 0 < delta_min <= threshold_min


def _human_time(hhmm: str | None) -> str:
    """Format a "HH:MM" clock string as "19h" / "19h30", matching opening hours."""
    if not hhmm or ":" not in hhmm:
        return hhmm or ""
    hour, minute = hhmm.split(":", 1)
    return f"{int(hour)}h" if minute == "00" else f"{int(hour)}h{minute}"


def _format_opening_hours() -> list[dict]:
    """Format Shop.opening_hours into display-ready lines for templates.

    Groups consecutive days with the same hours into ranges.
    Returns list of {label, hours} dicts, e.g.:
      [{"label": "Terça a Sábado", "hours": "7h às 19h"},
       {"label": "Domingo", "hours": "7h às 13h"},
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
            day_hours.append((day, f"{_fmt_time(info['open'])} às {_fmt_time(info['close'])}"))
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
