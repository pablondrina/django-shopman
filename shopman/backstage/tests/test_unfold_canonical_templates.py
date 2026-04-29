"""Guardrails for canonical Django Unfold Admin templates."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts import check_unfold_canonical


def test_admin_console_templates_do_not_hand_roll_visual_controls_or_tokens() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_unfold_canonical.py"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("content", "rule"),
    [
        ('<input type="text" name="q">', "raw-visible-input"),
        ('{% include "unfold/helpers/tab_items.html" with tabs_list=tabs %}', "direct-tab-items-helper"),
        ('<span class="material-symbols-outlined text-base">search</span>', "raw-material-icon"),
        ('<h2>Title</h2>', "raw-heading"),
        ('<span class="rounded-default bg-primary-100 text-primary-700">Draft</span>', "raw-label-badge"),
        ('<div class="gap-x-6"></div>', "noncanonical-layout-class"),
        ('<div class="tabular-nums"></div>', "unknown-unfold-css-class"),
        ('widget=forms.TextInput(attrs={"class": "tabular-nums"})', "unknown-unfold-css-class"),
        ('<div style="z-index: 1"></div>', "inline-style"),
        ('{% component "unfold/components/button.html" with class="h-8 px-2" %}{% endcomponent %}', "component-button-sizing"),
    ],
)
def test_unfold_gate_rejects_noncanonical_patterns(tmp_path: Path, content: str, rule: str) -> None:
    template = tmp_path / "template.html"
    template.write_text(content, encoding="utf-8")

    violations = check_unfold_canonical.scan_file(template, strict=False)

    assert rule in {violation.rule for violation in violations}


@pytest.mark.parametrize(
    ("content", "rule"),
    [
        ('<div class="fixed inset-0 z-[1000]"></div>', "raw-modal-overlay-location"),
        ('<details><summary>Historico</summary></details>', "raw-collapsible"),
        ('<div class="border border-base-200 rounded-default"></div>', "raw-visual-shell"),
    ],
)
def test_unfold_maturity_gate_rejects_hand_built_shells(tmp_path: Path, content: str, rule: str) -> None:
    template = tmp_path / "template.html"
    template.write_text(content, encoding="utf-8")

    violations = check_unfold_canonical.scan_file(template, strict=True)

    assert rule in {violation.rule for violation in violations}


def test_unfold_maturity_gate_accepts_authorized_modal_wrapper() -> None:
    modal = Path("shopman/backstage/templates/admin_console/unfold/modal.html")

    violations = check_unfold_canonical.scan_file(modal, strict=True)

    assert violations == []


def test_unfold_gate_accepts_authorized_compact_row_action_wrapper() -> None:
    row_action = Path("shopman/backstage/templates/admin_console/unfold/row_action_icon.html")

    violations = check_unfold_canonical.scan_file(row_action, strict=True)

    assert violations == []
