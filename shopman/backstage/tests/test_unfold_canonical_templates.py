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


def test_unfold_gate_default_scope_covers_admin_package_surfaces() -> None:
    files = {
        path.relative_to(check_unfold_canonical.ROOT).as_posix()
        for path in check_unfold_canonical.iter_templates(check_unfold_canonical.DEFAULT_TARGETS)
    }

    assert "shopman/backstage/templates/admin_console/production/index.html" in files
    assert "shopman/shop/templates/admin/index.html" in files
    assert "packages/refs/shopman/refs/templates/admin/refs/rename_confirm.html" in files
    assert "packages/orderman/shopman/orderman/templates/orderman/admin/session_change_form.html" in files
    assert "packages/offerman/shopman/offerman/contrib/admin_unfold/admin.py" in files


def test_unfold_surface_contract_rejects_unregistered_backstage_templates() -> None:
    new_template = check_unfold_canonical.ROOT / "shopman/backstage/templates/gestor/new_flow.html"

    violations = check_unfold_canonical.scan_surface_registry(
        extra_backstage_templates=(new_template,)
    )

    assert "unregistered-backstage-surface" in {violation.rule for violation in violations}


def test_unfold_surface_contract_requires_pos_runtime_templates_to_be_registered() -> None:
    new_template = check_unfold_canonical.ROOT / "shopman/backstage/templates/pos/new_flow.html"

    violations = check_unfold_canonical.scan_surface_registry(
        extra_backstage_templates=(new_template,)
    )

    assert "unregistered-backstage-surface" in {violation.rule for violation in violations}


def test_unfold_gate_can_scope_registered_admin_url_to_surface() -> None:
    surfaces = check_unfold_canonical.surfaces_for_url("/admin/operacao/producao/")

    assert [surface.id for surface in surfaces] == ["admin-console-production"]


def test_unfold_gate_rejects_unknown_admin_url_scope() -> None:
    assert check_unfold_canonical.surfaces_for_url("/admin/unknown/surface/") == ()


def test_unfold_gate_scoped_targets_are_limited_to_registered_surface() -> None:
    surfaces = check_unfold_canonical.surfaces_for_url("/admin/operacao/producao/criar/")
    files = {
        path.relative_to(check_unfold_canonical.ROOT).as_posix()
        for path in check_unfold_canonical.iter_templates(
            check_unfold_canonical.targets_for_surfaces(surfaces)
        )
    }

    assert "shopman/backstage/templates/admin_console/production/index.html" in files
    assert "shopman/shop/templates/admin/index.html" not in files


def test_unfold_installation_is_pinned_to_generated_official_inventory() -> None:
    violations = check_unfold_canonical.scan_unfold_installation()

    assert violations == []


def test_production_admin_surface_uses_official_custom_page_contract() -> None:
    violations = check_unfold_canonical.scan_surface_registry()
    rules = {violation.rule for violation in violations}

    assert "admin-page-missing-official-unfold-view-contract" not in rules
    assert "admin-surface-missing-unfold-primitive" not in rules
    assert "admin-surface-missing-unfold-controller-primitive" not in rules


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
        ("Piloto Admin/Unfold", "canonical-admin-transitional-copy"),
        ('{% component "unfold/components/button.html" with class="h-8 px-2" %}{% endcomponent %}', "component-button-sizing"),
        ('<label for="id_name">Nome</label>', "raw-form-label"),
        ('<a class="btn btn-outline-primary">Resolver</a>', "legacy-button-class"),
        ('<a href="/admin/">Admin</a>', "raw-anchor"),
        ('<p>Copy</p>', "raw-paragraph"),
        ('{% include "unfold/components/table.html" with table=table %}', "direct-component-include"),
        ('<div class="module">Conteudo</div>', "legacy-admin-module"),
        ('<div class="border border-base-200 rounded-default"></div>', "raw-visual-shell"),
        ('@action(dialog={"title": "Confirmar"})\ndef run(self, request, object_id): ...', "dialog-action-without-basedialogform"),
        (
            '{% component "unfold/components/card.html" with title="Mapa" %}\n'
            '{% component "unfold/components/text.html" %}Copy{% endcomponent %}\n'
            '{% component "unfold/components/table.html" with table=table card_included=1 %}{% endcomponent %}\n'
            '{% endcomponent %}',
            "card-included-table-body-prefix",
        ),
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
