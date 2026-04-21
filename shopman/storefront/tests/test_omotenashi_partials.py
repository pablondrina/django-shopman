"""Tests for urgency_badge and birthday_banner partials (WP-O3).

Both partials are driven purely by omotenashi_ctx — no DB access needed.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from django.template.loader import render_to_string
from django.utils import timezone

from shopman.storefront.omotenashi.context import (
    MOMENT_FECHADO,
    MOMENT_FECHANDO,
    MOMENT_MANHA,
    MOMENT_TARDE,
    OmotenashiContext,
)


def _ctx(
    moment: str = MOMENT_MANHA,
    is_birthday: bool = False,
    customer_name: str | None = None,
) -> OmotenashiContext:
    return OmotenashiContext(
        now=datetime.now(tz=timezone.get_current_timezone()),
        moment=moment,
        greeting="",
        shop_hint="",
        opens_at=None,
        closes_at=None,
        audience="anon",
        customer_name=customer_name,
        is_birthday=is_birthday,
        days_since_last_order=None,
        favorite_category=None,
    )


def _render(template_name: str, ctx: OmotenashiContext) -> str:
    return render_to_string(template_name, {"omotenashi_ctx": ctx})


# ── urgency_badge ─────────────────────────────────────────────────────


class TestUrgencyBadge:
    def test_shown_when_fechando(self):
        out = _render("storefront/partials/urgency_badge.html", _ctx(moment=MOMENT_FECHANDO))
        assert "Últimos pedidos" in out

    def test_hidden_when_manha(self):
        out = _render("storefront/partials/urgency_badge.html", _ctx(moment=MOMENT_MANHA))
        assert "Últimos pedidos" not in out

    def test_hidden_when_tarde(self):
        out = _render("storefront/partials/urgency_badge.html", _ctx(moment=MOMENT_TARDE))
        assert "Últimos pedidos" not in out

    def test_hidden_when_fechado(self):
        out = _render("storefront/partials/urgency_badge.html", _ctx(moment=MOMENT_FECHADO))
        assert "Últimos pedidos" not in out

    def test_has_dismiss_button(self):
        out = _render("storefront/partials/urgency_badge.html", _ctx(moment=MOMENT_FECHANDO))
        assert "Dispensar aviso" in out

    def test_has_alpine_dismiss(self):
        out = _render("storefront/partials/urgency_badge.html", _ctx(moment=MOMENT_FECHANDO))
        assert "show = false" in out


# ── birthday_banner ───────────────────────────────────────────────────


class TestBirthdayBanner:
    def test_shown_on_birthday_with_name(self):
        out = _render(
            "storefront/partials/birthday_banner.html",
            _ctx(is_birthday=True, customer_name="Maria"),
        )
        assert "aniversário" in out.lower()
        assert "Maria" in out

    def test_hidden_when_not_birthday(self):
        out = _render(
            "storefront/partials/birthday_banner.html",
            _ctx(is_birthday=False, customer_name="Maria"),
        )
        assert "aniversário" not in out.lower()

    def test_hidden_when_no_customer_name(self):
        out = _render(
            "storefront/partials/birthday_banner.html",
            _ctx(is_birthday=True, customer_name=None),
        )
        assert "aniversário" not in out.lower()

    def test_hidden_when_empty_customer_name(self):
        out = _render(
            "storefront/partials/birthday_banner.html",
            _ctx(is_birthday=True, customer_name=""),
        )
        assert "aniversário" not in out.lower()

    def test_renders_customer_name(self):
        out = _render(
            "storefront/partials/birthday_banner.html",
            _ctx(is_birthday=True, customer_name="João"),
        )
        assert "João" in out

    def test_has_dismiss_button(self):
        out = _render(
            "storefront/partials/birthday_banner.html",
            _ctx(is_birthday=True, customer_name="Ana"),
        )
        assert "Dispensar" in out

    def test_has_alpine_dismiss(self):
        out = _render(
            "storefront/partials/birthday_banner.html",
            _ctx(is_birthday=True, customer_name="Ana"),
        )
        assert "show = false" in out
