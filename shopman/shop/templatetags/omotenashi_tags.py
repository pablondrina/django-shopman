"""Template tags for omotenashi copy and human time formatting.

Usage:
    {% omotenashi "CART_EMPTY" %}                             {# renders resolved entry inline #}
    {% omotenashi "CART_EMPTY" as entry %}                    {# exposes .title / .message #}
    {% omotenashi "CART_EMPTY" moment="manha" as entry %}     {# override moment #}
    {% omotenashi "CART_EMPTY" audience="returning" as e %}   {# override audience #}

    {{ order.created_at|human_time }}          {# "há 3 min" #}
    {% human_eta order.eta %}                  {# "pronto por volta das 11h20" #}
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django import template
from django.utils import timezone

from shopman.shop.omotenashi import resolve_copy
from shopman.shop.omotenashi.context import AUDIENCE_ANON
from shopman.shop.omotenashi.copy import CopyEntry

logger = logging.getLogger(__name__)

register = template.Library()


# ── {% omotenashi KEY [moment=...] [audience=...] [as VAR] %} ──────────


@register.simple_tag(takes_context=True)
def omotenashi(context, key: str, moment: str | None = None, audience: str | None = None):
    """Resolve a copy entry with cascade (DB → code defaults → neutral fallback).

    `moment` and `audience` kwargs override the values inferred from
    `omotenashi_ctx` (the context processor). When the cascade ends with an
    empty entry — i.e. neither DB nor defaults have the key — a WARNING is
    logged so the missing entry surfaces in operational logs.
    """
    ctx = context.get("omotenashi_ctx")
    effective_moment = moment if moment is not None else getattr(ctx, "moment", "*")
    effective_audience = (
        audience if audience is not None else getattr(ctx, "audience", AUDIENCE_ANON)
    )
    entry = resolve_copy(key, moment=effective_moment, audience=effective_audience)
    if not entry:
        logger.warning(
            "omotenashi: key=%r moment=%r audience=%r resolved to empty entry",
            key,
            effective_moment,
            effective_audience,
        )
        return CopyEntry()
    return entry


# ── {{ value|human_time }} ─────────────────────────────────────────────


@register.filter
def human_time(value) -> str:
    """Humanise a datetime relative to now: 'agora', 'há 3 min', 'há 2 h', 'ontem', 'há 5 dias'.

    Returns empty string for invalid/None input — never raises in templates.
    """
    if not isinstance(value, datetime):
        return ""
    now = timezone.now()
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    delta = now - value
    seconds = int(delta.total_seconds())
    if seconds < 0:
        # Future — delegate to human_eta semantics
        return _future_phrase(value, -seconds)
    if seconds < 60:
        return "agora"
    minutes = seconds // 60
    if minutes < 60:
        return f"há {minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"há {hours} h"
    days = hours // 24
    if days == 1:
        return "ontem"
    if days < 7:
        return f"há {days} dias"
    weeks = days // 7
    if weeks < 5:
        return f"há {weeks} sem"
    months = days // 30
    if months < 12:
        return f"há {months} meses"
    years = days // 365
    return f"há {years} ano" + ("s" if years > 1 else "")


# ── {% human_eta value %} ──────────────────────────────────────────────


@register.simple_tag
def human_eta(value) -> str:
    """Format an ETA datetime as 'pronto por volta das 11h20'.

    If the value is a timedelta, returns 'em 12 min' / 'em 1h30'.
    """
    if isinstance(value, datetime):
        return _future_phrase(value, None)
    if isinstance(value, timedelta):
        seconds = int(value.total_seconds())
        if seconds < 60:
            return "em instantes"
        minutes = seconds // 60
        if minutes < 60:
            return f"em {minutes} min"
        hours = minutes // 60
        rem = minutes % 60
        return f"em {hours}h{rem:02d}" if rem else f"em {hours}h"
    return ""


def _future_phrase(target: datetime, remaining_seconds: int | None) -> str:
    """Phrase a future datetime in a human way."""
    now = timezone.now()
    if timezone.is_naive(target):
        target = timezone.make_aware(target, timezone.get_current_timezone())
    if remaining_seconds is None:
        remaining_seconds = int((target - now).total_seconds())
    if remaining_seconds <= 0:
        return "agora"
    if remaining_seconds < 60:
        return "em instantes"
    minutes = remaining_seconds // 60
    if minutes < 60:
        return f"em {minutes} min"
    local = timezone.localtime(target)
    hh, mm = local.hour, local.minute
    hhmm = f"{hh}h{mm:02d}" if mm else f"{hh}h"
    if local.date() == timezone.localdate():
        return f"por volta das {hhmm}"
    return f"amanhã às {hhmm}"
