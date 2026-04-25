"""OmotenashiContext — single source of truth for temporal + personal context.

Reads the current time, the shop's opening hours, and any available customer
signal (name, birthday, history) and reduces them to a frozen dataclass that
templates, views, and copy resolution consume.

This replaces Alpine-side `new Date().getHours()` duplication scattered across
`home.html`, `temporal_greeting.html`, and ad-hoc views.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from django.http import HttpRequest
from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Moments of the day ─────────────────────────────────────────────────
#
# These are derived from hour-of-day crossed with the shop's opening state.
# A moment is a coarse-grained temporal lens — copy keys vary by moment when
# tone would shift (e.g. "cart empty at 7h" vs "cart empty at 18h closing").

MOMENT_MADRUGADA = "madrugada"   # shop closed, pre-opening
MOMENT_MANHA = "manha"           # morning, shop open
MOMENT_ALMOCO = "almoco"         # lunch
MOMENT_TARDE = "tarde"           # afternoon
MOMENT_FECHANDO = "fechando"     # ≤ 1h to closing
MOMENT_FECHADO = "fechado"       # shop closed, post-closing

ALL_MOMENTS = (
    MOMENT_MADRUGADA,
    MOMENT_MANHA,
    MOMENT_ALMOCO,
    MOMENT_TARDE,
    MOMENT_FECHANDO,
    MOMENT_FECHADO,
)

# ── Audience ───────────────────────────────────────────────────────────

AUDIENCE_ANON = "anon"           # not authenticated
AUDIENCE_NEW = "new"             # authenticated, 0 orders
AUDIENCE_RETURNING = "returning" # 1..N-1 orders
AUDIENCE_VIP = "vip"             # ≥ N orders (configurable)

VIP_ORDER_THRESHOLD = 10

ALL_AUDIENCES = (AUDIENCE_ANON, AUDIENCE_NEW, AUDIENCE_RETURNING, AUDIENCE_VIP)


# ── Dataclass ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OmotenashiContext:
    # QUANDO
    now: datetime
    moment: str
    greeting: str
    shop_hint: str
    opens_at: str | None
    closes_at: str | None

    # QUEM
    audience: str
    customer_name: str | None
    is_birthday: bool
    days_since_last_order: int | None
    favorite_category: str | None

    # ── Factories ─────────────────────────────────────────────────

    @classmethod
    def from_request(cls, request: HttpRequest | None) -> OmotenashiContext:
        """Build context from an HTTP request. Safe even when request is None."""
        now = timezone.localtime()
        hours = _shop_hours_for(now)
        moment = _compute_moment(now, hours)
        greeting = _compute_greeting(now.hour)
        opens_at = hours.get("open") if hours else None
        closes_at = hours.get("close") if hours else None
        shop_hint = _compute_shop_hint(moment, opens_at, closes_at)

        audience, customer_name, is_birthday, days_since, fav_cat = _customer_signals(request, now.date())

        return cls(
            now=now,
            moment=moment,
            greeting=greeting,
            shop_hint=shop_hint,
            opens_at=opens_at,
            closes_at=closes_at,
            audience=audience,
            customer_name=customer_name,
            is_birthday=is_birthday,
            days_since_last_order=days_since,
            favorite_category=fav_cat,
        )

    # ── Helpers for templates ─────────────────────────────────────

    @property
    def is_open(self) -> bool:
        return self.moment in (MOMENT_MANHA, MOMENT_ALMOCO, MOMENT_TARDE, MOMENT_FECHANDO)

    @property
    def greeting_with_name(self) -> str:
        if self.customer_name:
            return f"{self.greeting}, {self.customer_name}"
        return self.greeting


# ── Internals ──────────────────────────────────────────────────────────


def _shop_hours_for(now: datetime) -> dict[str, str] | None:
    """Return {"open": "07:00", "close": "19:00"} for today, or None if closed."""
    try:
        from shopman.shop.models import Shop
    except Exception:
        return None
    shop = Shop.load()
    if not shop or not getattr(shop, "opening_hours", None):
        return None
    day_name = now.strftime("%A").lower()
    hours = shop.opening_hours.get(day_name)
    if not hours or not hours.get("open") or not hours.get("close"):
        return None
    return hours


def _compute_moment(now: datetime, hours: dict[str, str] | None) -> str:
    """Reduce current time to one of six moments."""
    if not hours:
        return MOMENT_FECHADO if now.hour >= 12 else MOMENT_MADRUGADA

    open_t = time.fromisoformat(hours["open"])
    close_t = time.fromisoformat(hours["close"])
    current = now.time()

    if current < open_t:
        return MOMENT_MADRUGADA
    if current >= close_t:
        return MOMENT_FECHADO

    # Open window — subdivide by meal time and proximity to closing.
    from datetime import datetime as _dt
    from datetime import timedelta

    close_dt = _dt.combine(now.date(), close_t, tzinfo=now.tzinfo)
    if close_dt - now <= timedelta(hours=1):
        return MOMENT_FECHANDO
    h = now.hour
    if h < 11:
        return MOMENT_MANHA
    if h < 14:
        return MOMENT_ALMOCO
    return MOMENT_TARDE


def _compute_greeting(hour: int) -> str:
    if hour < 5:
        return "Boa noite"
    if hour < 12:
        return "Bom dia"
    if hour < 18:
        return "Boa tarde"
    return "Boa noite"


def _compute_shop_hint(moment: str, opens_at: str | None, closes_at: str | None) -> str:
    """Short, contextual line about the shop's current state."""
    if moment == MOMENT_FECHADO and opens_at:
        return f"Fechado · abre {_fmt(opens_at)}"
    if moment == MOMENT_MADRUGADA and opens_at:
        return f"Abrimos às {_fmt(opens_at)}"
    if moment == MOMENT_FECHANDO and closes_at:
        return f"Últimos pedidos · fechamos às {_fmt(closes_at)}"
    if closes_at:
        return f"Aberto até {_fmt(closes_at)}"
    return ""


def _fmt(hhmm: str) -> str:
    """'07:00' → '7h'; '07:30' → '7h30'."""
    parts = hhmm.split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    return f"{h}h{m:02d}" if m else f"{h}h"


def _customer_signals(
    request: HttpRequest | None, today: date
) -> tuple[str, str | None, bool, int | None, str | None]:
    """Return (audience, first_name, is_birthday, days_since_last_order, fav_category)."""
    if request is None:
        return AUDIENCE_ANON, None, False, None, None

    info = getattr(request, "customer", None)
    if info is None:
        return AUDIENCE_ANON, None, False, None, None

    name = (info.name or "").split()[0] if info.name else None

    # Pull birthday and history from Guestman Customer.
    is_birthday = False
    days_since = None
    fav_cat = None
    try:
        from shopman.guestman.models import Customer
        customer = Customer.objects.filter(uuid=info.uuid).first()
        if customer:
            is_birthday = _is_birthday(customer.birthday, today)
            days_since, fav_cat = _history_signals(customer)
    except Exception:
        logger.debug("omotenashi._who: customer lookup failed", exc_info=True)

    audience = _audience_for(days_since)
    return audience, name, is_birthday, days_since, fav_cat


def _is_birthday(birthday: date | None, today: date) -> bool:
    if not birthday:
        return False
    # ±0 days: treat only the actual date. If we ever want a tolerance window,
    # it becomes a config, not a magic number here.
    return birthday.month == today.month and birthday.day == today.day


def _history_signals(customer: Any) -> tuple[int | None, str | None]:
    """Return (days_since_last_order, favorite_category_name_or_none).

    Soft-coupled to Orderman: if the Order model isn't available or the customer
    has no orders, we return (None, None) silently. This keeps context usable in
    fresh installs without seed data.
    """
    try:
        from shopman.orderman.models import Order
    except Exception:
        return None, None

    last = (
        Order.objects.filter(handle_type="customer", handle_ref=str(customer.uuid))
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    if not last:
        return None, None

    days_since = (timezone.now() - last).days
    # Favorite category — deliberately left as None here; to be filled by
    # customer_summary (Guestman) in a follow-up WP. We don't query it inline
    # to avoid hot-path DB work on every request.
    return days_since, None


def _audience_for(days_since: int | None) -> str:
    if days_since is None:
        return AUDIENCE_NEW
    # Order count proxy: if we ever need exact counts, replace days_since with
    # an .aggregate(Count). For now, presence of any order ⇒ returning.
    return AUDIENCE_RETURNING
