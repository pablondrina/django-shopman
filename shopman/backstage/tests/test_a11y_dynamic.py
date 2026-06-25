"""Dynamic accessibility checks — render surfaces with the Django test client and
parse the HTML to verify ARIA, landmarks, label associations, button texts.

Static checks live in test_a11y_backstage_baseline. These test the actual response
HTML so future template regressions surface here.
"""

from __future__ import annotations

import re

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from shopman.shop.models import Shop

HEADING_RE = re.compile(r"<h([1-6])\b[^>]*>", re.IGNORECASE)
INPUT_RE = re.compile(r"<input\b[^>]*>", re.IGNORECASE)
BUTTON_RE = re.compile(r"<button\b[^>]*>(.*?)</button>", re.IGNORECASE | re.DOTALL)
ARIA_LABEL_RE = re.compile(r'aria-label\s*=\s*"[^"]+"')
TYPE_RE = re.compile(r'type\s*=\s*"([^"]+)"', re.IGNORECASE)
ID_RE = re.compile(r'\bid\s*=\s*"([^"]+)"', re.IGNORECASE)
NAME_RE = re.compile(r'\bname\s*=\s*"([^"]+)"', re.IGNORECASE)
LABEL_FOR_RE = re.compile(r'<label[^>]*\bfor\s*=\s*"([^"]+)"', re.IGNORECASE)
ROLE_DIALOG_RE = re.compile(r'<[^>]+role\s*=\s*"dialog"[^>]*>', re.IGNORECASE)


@pytest.fixture
def superuser(db):
    Shop.objects.create(name="Loja")
    return User.objects.create_superuser("a11y-admin", "a11y@test.com", "pw")


def _heading_levels(html: str) -> list[int]:
    return [int(m.group(1)) for m in HEADING_RE.finditer(html)]


def _assert_no_heading_level_jump(html: str, surface: str) -> None:
    levels = _heading_levels(html)
    if not levels:
        return
    seen = {levels[0]}
    for prev, curr in zip(levels, levels[1:], strict=False):
        seen.add(curr)
        if curr > prev + 1:
            raise AssertionError(
                f"{surface}: heading hierarchy jump from h{prev} to h{curr} (levels seen: {sorted(seen)})"
            )


def _buttons_have_accessible_name(html: str, surface: str) -> None:
    """Every <button> element must contain visible text or an aria-label."""
    nameless: list[str] = []
    for match in BUTTON_RE.finditer(html):
        opening = html[match.start() : match.start(1)]
        body = match.group(1)
        # strip nested tags then whitespace
        text = re.sub(r"<[^>]+>", "", body).strip()
        if text:
            continue
        if ARIA_LABEL_RE.search(opening):
            continue
        # title attribute also reasonable
        if 'title="' in opening:
            continue
        nameless.append(opening[:120])
    assert not nameless, f"{surface}: buttons without accessible name:\n  " + "\n  ".join(nameless[:5])


def _inputs_have_label(html: str, surface: str) -> None:
    """Every form input (text/number/email/etc.) must have a label, aria-label, or aria-labelledby."""
    label_targets = set(LABEL_FOR_RE.findall(html))
    skipped_types = {"hidden", "submit", "button", "image", "reset"}
    unlabeled: list[str] = []
    for match in INPUT_RE.finditer(html):
        tag = match.group(0)
        type_match = TYPE_RE.search(tag)
        input_type = (type_match.group(1).lower() if type_match else "text")
        if input_type in skipped_types:
            continue
        if ARIA_LABEL_RE.search(tag) or "aria-labelledby" in tag:
            continue
        id_match = ID_RE.search(tag)
        if id_match and id_match.group(1) in label_targets:
            continue
        # search/lookup widgets often have placeholder + visually-hidden label upstream
        # accept if surrounded by <label> via name lookup or there's an explicit role
        name_match = NAME_RE.search(tag)
        if name_match and '<label' in html and name_match.group(1) in html:
            # weak proxy — only if a <label> wraps something with the same name
            wrapped = re.search(rf"<label[^>]*>[^<]*<input[^>]*name=\"{re.escape(name_match.group(1))}\"", html)
            if wrapped:
                continue
        unlabeled.append(tag[:140])
    assert not unlabeled, f"{surface}: inputs without label/aria-label:\n  " + "\n  ".join(unlabeled[:5])


def _dialogs_are_well_formed(html: str, surface: str) -> None:
    """role=dialog requires aria-modal and a labelling reference."""
    issues: list[str] = []
    for match in ROLE_DIALOG_RE.finditer(html):
        tag = match.group(0)
        if 'aria-modal="true"' not in tag:
            issues.append(f"missing aria-modal: {tag[:120]}")
        if "aria-labelledby" not in tag and "aria-label" not in tag:
            issues.append(f"missing aria-labelledby/aria-label: {tag[:120]}")
    assert not issues, f"{surface}: dialog landmarks malformed:\n  " + "\n  ".join(issues)


def _has_main_landmark(html: str, surface: str) -> None:
    assert "<main" in html or 'role="main"' in html, f"{surface}: missing <main> landmark"


# ── Surfaces ───────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_a11y_producao_matriz(client, superuser):
    client.force_login(superuser)
    response = client.get(reverse("admin_console_production"))
    assert response.status_code == 200
    html = response.content.decode("utf-8")

    _has_main_landmark(html, "Produção")
    _assert_no_heading_level_jump(html, "Produção")
    _buttons_have_accessible_name(html, "Produção")
    _dialogs_are_well_formed(html, "Produção")


@pytest.mark.django_db
def test_a11y_producao_dashboard(client, superuser):
    client.force_login(superuser)
    response = client.get(reverse("admin_console_production_dashboard"))
    assert response.status_code == 200
    html = response.content.decode("utf-8")

    _has_main_landmark(html, "Dashboard produção")
    _assert_no_heading_level_jump(html, "Dashboard produção")
    _buttons_have_accessible_name(html, "Dashboard produção")


@pytest.mark.django_db
def test_a11y_producao_kds(client, superuser):
    client.force_login(superuser)
    response = client.get(reverse("backstage:production_kds"))
    assert response.status_code == 200
    html = response.content.decode("utf-8")

    _has_main_landmark(html, "KDS produção")
    _buttons_have_accessible_name(html, "KDS produção")


@pytest.mark.django_db
def test_a11y_producao_relatorios(client, superuser):
    client.force_login(superuser)
    response = client.get(reverse("admin_console_production_reports"))
    assert response.status_code == 200
    html = response.content.decode("utf-8")

    _has_main_landmark(html, "Relatórios")
    _assert_no_heading_level_jump(html, "Relatórios")
    _buttons_have_accessible_name(html, "Relatórios")


@pytest.mark.django_db
def test_a11y_fechamento(client, superuser):
    client.force_login(superuser)
    response = client.get(reverse("admin_console_day_closing"))
    assert response.status_code == 200
    html = response.content.decode("utf-8")

    _has_main_landmark(html, "Fechamento")
    _buttons_have_accessible_name(html, "Fechamento")


