"""Tests for the omotenashi infrastructure: context, copy resolver, model, tags."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest
from django.template import Context, Template
from django.utils import timezone

from shopman.shop.models import OmotenashiCopy
from shopman.storefront.omotenashi import OmotenashiContext, resolve_copy
from shopman.storefront.omotenashi.context import (
    AUDIENCE_ANON,
    AUDIENCE_RETURNING,
    MOMENT_ALMOCO,
    MOMENT_FECHADO,
    MOMENT_FECHANDO,
    MOMENT_MADRUGADA,
    MOMENT_MANHA,
    MOMENT_TARDE,
)
from shopman.storefront.omotenashi.copy import (
    OMOTENASHI_DEFAULTS,
    invalidate_cache,
)

# ── OmotenashiContext ──────────────────────────────────────────────────


@pytest.fixture
def shop_7_to_19(db):
    """A shop open every day from 07:00 to 19:00."""
    from shopman.shop.models import Shop

    shop = Shop.load()
    if not shop:
        shop = Shop.objects.create(name="Test Padaria")
    shop.opening_hours = {
        day: {"open": "07:00", "close": "19:00"}
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    }
    shop.save()
    from django.core.cache import cache as dj_cache

    from shopman.shop.models.shop import SHOP_CACHE_KEY

    dj_cache.delete(SHOP_CACHE_KEY)
    return shop


def _freeze(hour: int, minute: int = 0) -> datetime:
    tz = timezone.get_current_timezone()
    return datetime(2026, 4, 15, hour, minute, tzinfo=tz)  # Wednesday


@pytest.mark.parametrize(
    "hour,expected_moment",
    [
        (3, MOMENT_MADRUGADA),
        (8, MOMENT_MANHA),
        (12, MOMENT_ALMOCO),
        (15, MOMENT_TARDE),
        (18, MOMENT_FECHANDO),  # ≤ 1h to closing (19:00)
        (20, MOMENT_FECHADO),
    ],
)
def test_moment_follows_hour_and_opening_hours(shop_7_to_19, hour, expected_moment):
    frozen = _freeze(hour)
    with patch("django.utils.timezone.localtime", return_value=frozen):
        ctx = OmotenashiContext.from_request(None)
    assert ctx.moment == expected_moment


def test_greeting_matches_time_of_day(shop_7_to_19):
    with patch("django.utils.timezone.localtime", return_value=_freeze(8)):
        assert OmotenashiContext.from_request(None).greeting == "Bom dia"
    with patch("django.utils.timezone.localtime", return_value=_freeze(14)):
        assert OmotenashiContext.from_request(None).greeting == "Boa tarde"
    with patch("django.utils.timezone.localtime", return_value=_freeze(20)):
        assert OmotenashiContext.from_request(None).greeting == "Boa noite"


def test_shop_hint_reflects_state(shop_7_to_19):
    with patch("django.utils.timezone.localtime", return_value=_freeze(18, 30)):
        ctx = OmotenashiContext.from_request(None)
    assert "fechamos" in ctx.shop_hint.lower()
    with patch("django.utils.timezone.localtime", return_value=_freeze(3)):
        ctx = OmotenashiContext.from_request(None)
    assert "7h" in ctx.shop_hint


def test_anonymous_request_has_anon_audience(rf, shop_7_to_19):
    request = rf.get("/")
    with patch("django.utils.timezone.localtime", return_value=_freeze(10)):
        ctx = OmotenashiContext.from_request(request)
    assert ctx.audience == AUDIENCE_ANON
    assert ctx.customer_name is None
    assert ctx.is_birthday is False


def test_is_open_property(shop_7_to_19):
    with patch("django.utils.timezone.localtime", return_value=_freeze(10)):
        assert OmotenashiContext.from_request(None).is_open is True
    with patch("django.utils.timezone.localtime", return_value=_freeze(3)):
        assert OmotenashiContext.from_request(None).is_open is False


# ── resolve_copy (cascade) ─────────────────────────────────────────────


def test_resolver_falls_back_to_code_default(db):
    entry = resolve_copy("CART_EMPTY", moment=MOMENT_MANHA, audience=AUDIENCE_ANON)
    assert entry.title == "Carrinho vazio"


def test_resolver_uses_audience_specific_when_present(db):
    entry = resolve_copy("CART_EMPTY", moment=MOMENT_MANHA, audience=AUDIENCE_RETURNING)
    assert "repetir" in entry.message.lower()


def test_every_key_resolves_in_at_least_one_moment(db):
    # Every key must resolve for at least one (moment, audience) — i.e. every
    # key in the defaults dict is reachable. Moment-specific keys (e.g. the
    # tomorrow hook) are intentionally empty outside their window.
    all_moments = (
        MOMENT_MADRUGADA, MOMENT_MANHA, MOMENT_ALMOCO,
        MOMENT_TARDE, MOMENT_FECHANDO, MOMENT_FECHADO,
    )
    for key in OMOTENASHI_DEFAULTS.keys():
        resolved = [resolve_copy(key, moment=m, audience=AUDIENCE_ANON) for m in all_moments]
        assert any(resolved), f"{key} never resolves to a non-empty entry"


def test_db_override_beats_code_default(db):
    OmotenashiCopy.objects.create(
        key="CART_EMPTY", moment="*", audience="*", title="CUSTOM", message="override"
    )
    entry = resolve_copy("CART_EMPTY", moment=MOMENT_MANHA, audience=AUDIENCE_ANON)
    assert entry.title == "CUSTOM"
    assert entry.message == "override"


def test_db_inactive_row_falls_back_to_default(db):
    OmotenashiCopy.objects.create(
        key="CART_EMPTY",
        moment="*",
        audience="*",
        title="INACTIVE",
        active=False,
    )
    entry = resolve_copy("CART_EMPTY", moment=MOMENT_MANHA, audience=AUDIENCE_ANON)
    assert entry.title != "INACTIVE"


def test_db_cache_invalidates_on_save(db):
    invalidate_cache()
    resolve_copy("CART_EMPTY", moment=MOMENT_MANHA, audience=AUDIENCE_ANON)  # prime cache
    OmotenashiCopy.objects.create(key="CART_EMPTY", moment="*", audience="*", title="NEW")
    entry = resolve_copy("CART_EMPTY", moment=MOMENT_MANHA, audience=AUDIENCE_ANON)
    assert entry.title == "NEW"


def test_unknown_key_returns_empty_entry(db):
    entry = resolve_copy("DOES_NOT_EXIST", moment=MOMENT_MANHA, audience=AUDIENCE_ANON)
    assert not entry


# ── Template tag ───────────────────────────────────────────────────────


def test_omotenashi_tag_renders_message(db, rf, shop_7_to_19):
    request = rf.get("/")
    with patch("django.utils.timezone.localtime", return_value=_freeze(8)):
        ctx = OmotenashiContext.from_request(request)
    tpl = Template(
        "{% load omotenashi_tags %}{% omotenashi 'MENU_SUBTITLE' as e %}{{ e.message }}"
    )
    out = tpl.render(Context({"omotenashi_ctx": ctx}))
    assert "fresquinho" in out.lower()


def test_human_time_filter():
    tpl = Template("{% load omotenashi_tags %}{{ when|human_time }}")
    now = timezone.now()
    assert tpl.render(Context({"when": now})) == "agora"
    assert tpl.render(Context({"when": now - timedelta(minutes=3)})) == "há 3 min"
    assert tpl.render(Context({"when": now - timedelta(hours=5)})) == "há 5 h"
    assert tpl.render(Context({"when": now - timedelta(days=1)})) == "ontem"
    assert tpl.render(Context({"when": None})) == ""


def test_human_eta_tag_with_timedelta():
    tpl = Template("{% load omotenashi_tags %}{% human_eta v %}")
    assert tpl.render(Context({"v": timedelta(minutes=12)})) == "em 12 min"
    assert tpl.render(Context({"v": timedelta(hours=1, minutes=30)})) == "em 1h30"


def test_human_eta_tag_with_future_datetime_today():
    tpl = Template("{% load omotenashi_tags %}{% human_eta v %}")
    # +2h guarantees ≥60 min so we never hit the "em X min" branch
    later = timezone.localtime() + timedelta(hours=2)
    out = tpl.render(Context({"v": later}))
    assert "por volta das" in out or "amanhã" in out


# ── Birthday detection ─────────────────────────────────────────────────


def test_is_birthday_matches_month_and_day():
    from shopman.storefront.omotenashi.context import _is_birthday

    assert _is_birthday(date(1990, 4, 17), date(2026, 4, 17)) is True
    assert _is_birthday(date(1990, 4, 18), date(2026, 4, 17)) is False
    assert _is_birthday(None, date(2026, 4, 17)) is False
