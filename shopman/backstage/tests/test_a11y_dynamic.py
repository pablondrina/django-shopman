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

INPUT_RE = re.compile(r"<input\b[^>]*>", re.IGNORECASE)
BUTTON_RE = re.compile(r"<button\b[^>]*>(.*?)</button>", re.IGNORECASE | re.DOTALL)
ARIA_LABEL_RE = re.compile(r'aria-label\s*=\s*"[^"]+"')
TYPE_RE = re.compile(r'type\s*=\s*"([^"]+)"', re.IGNORECASE)
ID_RE = re.compile(r'\bid\s*=\s*"([^"]+)"', re.IGNORECASE)
NAME_RE = re.compile(r'\bname\s*=\s*"([^"]+)"', re.IGNORECASE)
LABEL_FOR_RE = re.compile(r'<label[^>]*\bfor\s*=\s*"([^"]+)"', re.IGNORECASE)
@pytest.fixture
def superuser(db):
    Shop.objects.create(name="Loja")
    return User.objects.create_superuser("a11y-admin", "a11y@test.com", "pw")


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


def _has_main_landmark(html: str, surface: str) -> None:
    assert "<main" in html or 'role="main"' in html, f"{surface}: missing <main> landmark"


# ── Surfaces ───────────────────────────────────────────────────────────


# A produção inteira (chão, matriz, dashboard e relatórios) é do Fournil
# (surfaces/production-nuxt): a11y testada na suite do app Nuxt. As telas
# Django (HTMX na Fase 4, console Admin/Unfold no WP-ADM-7d) foram removidas.


@pytest.mark.django_db
def test_a11y_fechamento(client, superuser):
    client.force_login(superuser)
    response = client.get(reverse("admin_console_day_closing"))
    assert response.status_code == 200
    html = response.content.decode("utf-8")

    _has_main_landmark(html, "Fechamento")
    _buttons_have_accessible_name(html, "Fechamento")


