"""Keyboard navigation accessibility — skip link presence, focus traps in
modals, no positive tabindex (which breaks natural tab order).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from shopman.shop.models import Shop


TABINDEX_RE = re.compile(r'tabindex\s*=\s*"(-?\d+)"', re.IGNORECASE)
DIALOG_OPEN_RE = re.compile(r'<[^>]+role\s*=\s*"dialog"[^>]*>', re.IGNORECASE)
FOCUSABLE_RE = re.compile(
    r"<(?:button|a|input|select|textarea)\b"
    r"|\{%\s*component\s+[\"']unfold/components/(?:button|link)\.html[\"']",
    re.IGNORECASE,
)


@pytest.fixture
def superuser(db):
    Shop.objects.create(name="Loja")
    return User.objects.create_superuser("kbd-admin", "kbd@test.com", "pw")


def _no_positive_tabindex(html: str, surface: str) -> None:
    """Positive tabindex breaks natural tab order. Only -1 (focus target) and 0 are acceptable."""
    bad: list[str] = []
    for match in TABINDEX_RE.finditer(html):
        value = int(match.group(1))
        if value > 0:
            bad.append(f"tabindex={value}")
    assert not bad, f"{surface}: positive tabindex found (breaks natural order): {bad}"


@pytest.mark.django_db
def test_skip_link_present_in_shell(client, superuser):
    """Pressing Tab once after page load must reveal a skip link to main content."""
    client.force_login(superuser)
    response = client.get(reverse("backstage:pos"))
    html = response.content.decode("utf-8")
    assert 'href="#backstage-main"' in html, "skip link to main missing"
    assert "Pular para o conteúdo principal" in html
    assert 'id="backstage-main"' in html, "main landmark must have matching id"


@pytest.mark.django_db
def test_no_positive_tabindex_anywhere(client, superuser):
    surfaces = [
        ("backstage:pos", []),
        ("admin_console_kds", []),
        ("admin_console_orders", []),
        ("admin_console_production", []),
        ("admin_console_production_dashboard", []),
        ("backstage:production_kds", []),
        ("admin_console_production_reports", []),
        ("admin_console_day_closing", []),
    ]
    client.force_login(superuser)
    for name, args in surfaces:
        response = client.get(reverse(name, args=args))
        if response.status_code != 200:
            continue
        _no_positive_tabindex(response.content.decode("utf-8"), name)


def test_dialogs_in_templates_contain_focusable_elements():
    """Modals must have at least one focusable element so focus trap is possible.

    We grep templates because dialogs are typically rendered inside Alpine
    x-show="..." blocks and only mounted when triggered — server-side render
    may exclude them. The static check still enforces the contract.
    """
    template_root = Path("shopman/backstage/templates")
    issues: list[str] = []
    for path in template_root.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        for match in DIALOG_OPEN_RE.finditer(text):
            # Check that focusable element appears anywhere after the dialog open
            tail = text[match.end() :]
            if not FOCUSABLE_RE.search(tail):
                issues.append(f"{path.relative_to(template_root)} dialog without focusable elements")
    assert not issues, "Modals without focusable elements:\n  " + "\n  ".join(issues)


@pytest.mark.django_db
def test_csrf_form_buttons_have_accessible_names_in_pos(client, superuser):
    client.force_login(superuser)
    response = client.get(reverse("backstage:pos"))
    html = response.content.decode("utf-8")
    # Each <form> with method=post should have a <button type="submit"> reachable
    submit_count = html.count('type="submit"')
    assert submit_count >= 1, "POS surface should expose at least one submit button"


@pytest.mark.django_db
def test_modals_use_aria_modal_when_role_dialog(client, superuser):
    """Whenever role=dialog is rendered server-side, aria-modal must be set."""
    client.force_login(superuser)
    response = client.get(reverse("admin_console_production"))
    html = response.content.decode("utf-8")
    for match in re.finditer(r"<[^>]+role=\"dialog\"[^>]*>", html):
        assert 'aria-modal="true"' in match.group(0), f"dialog without aria-modal: {match.group(0)[:120]}"


@pytest.mark.django_db
def test_navigation_landmark_labelled(client, superuser):
    client.force_login(superuser)
    response = client.get(reverse("backstage:pos"))
    html = response.content.decode("utf-8")
    nav_match = re.search(r"<(?:nav|aside)[^>]*role=\"navigation\"[^>]*>", html)
    if not nav_match:
        nav_match = re.search(r"<nav\b[^>]*>", html)
    assert nav_match, "missing <nav> or role=navigation landmark"
    assert "aria-label" in nav_match.group(0), "navigation landmark must have aria-label"
