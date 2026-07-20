"""Janela de publicação — a hora certa de falar com o cliente.

Uma fornada que sai às 5h30 não vira post às 5h30: ninguém está olhando, e o
conteúdo chega frio justamente quando a pessoa acorda. A
``BroadcastRule.schedule`` declara as janelas em que a padaria quer aparecer;
um evento fora delas não perde o post, só espera a próxima abertura.

Formato de ``BroadcastRule.schedule``::

    {"type": "immediate"}                        # padrão — sai na hora
    {"type": "preferred_hours",
     "windows": [["07:00", "11:00"], ["15:00", "18:00"]],
     "weekdays": [0, 1, 2, 3, 4, 5]}             # 0 = segunda; ausente = todos

Puro e testável: só relógio e config, sem banco. Config quebrada nunca segura
um post — na dúvida publica agora, porque marketing não pode virar gargalo da
operação.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from django.utils import timezone

PREFERRED_HOURS = "preferred_hours"

#: Hoje + uma semana cheia: cobre qualquer combinação de ``weekdays``.
MAX_LOOKAHEAD_DAYS = 8

ALL_WEEKDAYS = frozenset(range(7))


def next_publish_at(schedule: dict | None, *, now: datetime | None = None):
    """Quando este post deve sair, ou ``None`` para "agora".

    Args:
        schedule: ``BroadcastRule.schedule``.
        now: relógio injetável (default: agora).

    Returns:
        ``None`` quando o momento atual já serve (tipo ``immediate``, config
        ausente ou inválida, ou estamos dentro de uma janela). Caso contrário,
        o início da próxima janela, timezone-aware.
    """
    if not isinstance(schedule, dict) or schedule.get("type") != PREFERRED_HOURS:
        return None

    windows = _windows(schedule.get("windows"))
    weekdays = _weekdays(schedule.get("weekdays"))
    if not windows or not weekdays:
        return None

    now = timezone.localtime(now or timezone.now())
    if _is_open(now, windows, weekdays):
        return None
    return _next_opening(now, windows, weekdays)


def describe(schedule: dict | None) -> str:
    """Resumo legível da janela, para o Admin e o card do gestor."""
    if not isinstance(schedule, dict) or schedule.get("type") != PREFERRED_HOURS:
        return "publica na hora"
    windows = _windows(schedule.get("windows"))
    if not windows:
        return "publica na hora"
    faixas = ", ".join(
        f"{start.strftime('%H:%M')} às {end.strftime('%H:%M')}" for start, end in windows
    )
    weekdays = _weekdays(schedule.get("weekdays"))
    if weekdays == ALL_WEEKDAYS:
        return f"publica entre {faixas}"
    dias = ", ".join(_WEEKDAY_NAMES[day] for day in sorted(weekdays))
    return f"publica entre {faixas} ({dias})"


_WEEKDAY_NAMES = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


# ── Cálculo ──────────────────────────────────────────────────────────


def _is_open(now: datetime, windows, weekdays) -> bool:
    if now.weekday() not in weekdays:
        return False
    return any(start <= now.time() < end for start, end in windows)


def _next_opening(now: datetime, windows, weekdays):
    """A primeira abertura de janela estritamente depois de ``now``."""
    for offset in range(MAX_LOOKAHEAD_DAYS):
        day = (now + timedelta(days=offset)).date()
        if day.weekday() not in weekdays:
            continue
        for start, _end in windows:
            candidate = _aware(datetime.combine(day, start))
            if candidate > now:
                return candidate
    return None


def _aware(value: datetime) -> datetime:
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


# ── Parsing tolerante ────────────────────────────────────────────────


def _windows(raw) -> list[tuple[time, time]]:
    """Pares ``[início, fim]`` válidos, ordenados. Entrada torta é ignorada.

    Janela que vira o dia (fim <= início) não existe aqui: padaria não publica
    de madrugada, e aceitar isso só criaria agendamento surpresa.
    """
    out: list[tuple[time, time]] = []
    for entry in raw or ():
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            continue
        start, end = _parse_time(entry[0]), _parse_time(entry[1])
        if start is None or end is None or end <= start:
            continue
        out.append((start, end))
    return sorted(out)


def _weekdays(raw) -> frozenset:
    """Dias permitidos (0 = segunda). Ausente ou inválido = a semana toda."""
    if raw is None:
        return ALL_WEEKDAYS
    days = set()
    for value in raw if isinstance(raw, (list, tuple, set)) else ():
        try:
            day = int(value)
        except (TypeError, ValueError):
            continue
        if 0 <= day <= 6:
            days.add(day)
    return frozenset(days) if days else ALL_WEEKDAYS


def _parse_time(value) -> time | None:
    if isinstance(value, time):
        return value
    try:
        hour, _, minute = str(value).partition(":")
        return time(int(hour), int(minute or 0))
    except (TypeError, ValueError):
        return None
