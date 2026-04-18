"""Tests for the `{% omotenashi %}` template tag (WP-GAP-03 Fase 1).

Covers:
1. Tag resolves via DB when an active record exists.
2. Tag falls back to code defaults when no DB record exists.
3. Tag logs WARNING when resolution reaches the ultimate empty fallback.
4. Tag infers `moment` / `audience` from the context processor.
5. Admin `reset_to_default` action → template goes back to the code default.
"""

from __future__ import annotations

import logging

import pytest
from django.template import Context, Template

from shopman.shop.models import OmotenashiCopy
from shopman.shop.omotenashi import OmotenashiContext
from shopman.shop.omotenashi.context import (
    AUDIENCE_ANON,
    AUDIENCE_RETURNING,
    MOMENT_MANHA,
    MOMENT_TARDE,
)
from shopman.shop.omotenashi.copy import invalidate_cache


def _render(tpl_src: str, **ctx) -> str:
    """Render a template with `omotenashi_ctx` defaulting to morning/anon."""
    ctx.setdefault("omotenashi_ctx", _ctx(MOMENT_MANHA, AUDIENCE_ANON))
    return Template(tpl_src).render(Context(ctx))


def _ctx(moment: str, audience: str) -> OmotenashiContext:
    """Build a bare OmotenashiContext with just moment/audience set — no DB hit."""
    from datetime import datetime

    from django.utils import timezone

    return OmotenashiContext(
        now=datetime.now(tz=timezone.get_current_timezone()),
        moment=moment,
        greeting="",
        shop_hint="",
        opens_at=None,
        closes_at=None,
        audience=audience,
        customer_name=None,
        is_birthday=False,
        days_since_last_order=None,
        favorite_category=None,
    )


# ── 1. DB override beats defaults ──────────────────────────────────────


@pytest.mark.django_db
def test_tag_renders_via_db_when_active_record_exists():
    invalidate_cache()
    OmotenashiCopy.objects.create(
        key="MENU_SUBTITLE",
        moment="*",
        audience="*",
        title="",
        message="Custom do banco",
        active=True,
    )
    out = _render(
        "{% load omotenashi_tags %}{% omotenashi 'MENU_SUBTITLE' as e %}{{ e.message }}"
    )
    assert out.strip() == "Custom do banco"


# ── 2. Fallback to code defaults ───────────────────────────────────────


@pytest.mark.django_db
def test_tag_falls_back_to_defaults_when_no_db_record():
    invalidate_cache()
    # MENU_SUBTITLE has a manha default: "Fresquinho do forno."
    out = _render(
        "{% load omotenashi_tags %}{% omotenashi 'MENU_SUBTITLE' as e %}{{ e.message }}"
    )
    assert "fresquinho" in out.lower()


# ── 3. WARNING log when key unknown ────────────────────────────────────


@pytest.mark.django_db
def test_tag_logs_warning_on_unknown_key(caplog):
    invalidate_cache()
    # The `shopman` logger has propagate=False in settings, so we attach the
    # caplog handler directly to the child logger that emits the warning.
    tag_logger = logging.getLogger("shopman.shop.templatetags.omotenashi_tags")
    tag_logger.addHandler(caplog.handler)
    caplog.set_level(logging.WARNING, logger="shopman.shop.templatetags.omotenashi_tags")
    try:
        out = _render(
            "{% load omotenashi_tags %}{% omotenashi 'DOES_NOT_EXIST_KEY' as e %}"
            "[{{ e.title }}|{{ e.message }}]"
        )
    finally:
        tag_logger.removeHandler(caplog.handler)
    assert out.strip() == "[|]"
    assert any(
        "DOES_NOT_EXIST_KEY" in record.getMessage() and record.levelno == logging.WARNING
        for record in caplog.records
    ), f"Expected WARNING mentioning the missing key, got: {[r.getMessage() for r in caplog.records]}"


# ── 4. Inference from context processor ────────────────────────────────


@pytest.mark.django_db
def test_tag_infers_moment_from_context_processor():
    invalidate_cache()
    # MENU_SUBTITLE has distinct defaults per moment.
    tpl = "{% load omotenashi_tags %}{% omotenashi 'MENU_SUBTITLE' as e %}{{ e.message }}"

    manha = Template(tpl).render(Context({"omotenashi_ctx": _ctx(MOMENT_MANHA, AUDIENCE_ANON)}))
    tarde = Template(tpl).render(Context({"omotenashi_ctx": _ctx(MOMENT_TARDE, AUDIENCE_ANON)}))

    assert manha.strip() != tarde.strip()
    assert "fresquinho" in manha.lower()
    assert "tarde" in tarde.lower()


@pytest.mark.django_db
def test_tag_kwarg_overrides_context_moment_and_audience():
    invalidate_cache()
    # Explicit kwargs win over context.
    out_default = _render(
        "{% load omotenashi_tags %}{% omotenashi 'CART_EMPTY' as e %}{{ e.title }}",
        omotenashi_ctx=_ctx(MOMENT_MANHA, AUDIENCE_ANON),
    )
    out_override = _render(
        "{% load omotenashi_tags %}"
        "{% omotenashi 'CART_EMPTY' audience='returning' as e %}{{ e.title }}",
        omotenashi_ctx=_ctx(MOMENT_MANHA, AUDIENCE_ANON),
    )
    assert "vazio" in out_default.lower()           # anon default
    assert "repetir" not in out_default.lower()
    # Returning audience has a different title in MOMENT_MANHA.
    assert out_override.strip() != out_default.strip()


# ── 5. Admin reset_to_default integration ──────────────────────────────


@pytest.mark.django_db
def test_reset_to_default_action_restores_code_default():
    invalidate_cache()
    override = OmotenashiCopy.objects.create(
        key="MENU_SUBTITLE",
        moment="*",
        audience="*",
        title="",
        message="CUSTOMISED",
        active=True,
    )
    # Override is in effect.
    out = _render(
        "{% load omotenashi_tags %}{% omotenashi 'MENU_SUBTITLE' as e %}{{ e.message }}"
    )
    assert out.strip() == "CUSTOMISED"

    # Admin action deactivates → cache invalidates → default returns.
    from shopman.shop.admin.omotenashi import OmotenashiCopyAdmin

    admin_instance = OmotenashiCopyAdmin(OmotenashiCopy, admin_site=None)
    admin_instance.message_user = lambda *a, **kw: None  # no-op
    admin_instance.reset_to_default(request=None, queryset=OmotenashiCopy.objects.filter(pk=override.pk))

    out_after = _render(
        "{% load omotenashi_tags %}{% omotenashi 'MENU_SUBTITLE' as e %}{{ e.message }}"
    )
    assert "fresquinho" in out_after.lower()
    assert "CUSTOMISED" not in out_after
