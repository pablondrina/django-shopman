"""Template tags for omotenashi copy and human time formatting.

Usage:
    {% omotenashi "CART_EMPTY" %}              {# renders the resolved message inline #}
    {% omotenashi "CART_EMPTY" as entry %}     {# exposes .title / .message #}
      <h2>{{ entry.title }}</h2>
      <p>{{ entry.message }}</p>

    {{ order.created_at|human_time }}          {# "há 3 min" #}
    {% human_eta order.eta %}                  {# "pronto por volta das 11h20" #}
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django import template
from django.utils import timezone

from shopman.shop.omotenashi import resolve_copy
from shopman.shop.omotenashi.context import AUDIENCE_ANON

register = template.Library()


# ── {% omotenashi KEY [as VAR] %} ──────────────────────────────────────


@register.simple_tag(takes_context=True)
def omotenashi(context, key: str):
    """Resolve a copy entry and return it. Renders inline if not captured with `as`.

    Uses the `omotenashi_ctx` provided by the context processor.
    """
    ctx = context.get("omotenashi_ctx")
    moment = getattr(ctx, "moment", "*")
    audience = getattr(ctx, "audience", AUDIENCE_ANON)
    return resolve_copy(key, moment=moment, audience=audience)


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
