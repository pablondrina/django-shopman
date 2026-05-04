#!/usr/bin/env python
"""Guard Admin templates against non-canonical Django Unfold controls."""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import re
from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/reference/unfold_canonical_inventory.md"
BACKSTAGE_TEMPLATES = ROOT / "shopman/backstage/templates"
BACKSTAGE_PROJECTIONS = ROOT / "shopman/backstage/projections"
APPROVED_MODAL_TEMPLATE = ROOT / "shopman/backstage/templates/admin_console/unfold/modal.html"
APPROVED_ROW_ACTION_TEMPLATE = ROOT / "shopman/backstage/templates/admin_console/unfold/row_action_icon.html"
APPROVED_MODAL_OVERLAY_CLASS = "backdrop-blur-xs bg-base-900/80 flex flex-col fixed inset-0 p-4 lg:p-32 z-[1000]"
APPROVED_MODAL_PANEL_CLASS = (
    "bg-white flex flex-col max-w-sm min-h-0 mx-auto overflow-hidden rounded-default shadow-lg "
    "w-full dark:bg-base-800"
)
APPROVED_ROW_ACTION_CLASS = (
    "bg-white border border-base-200 cursor-pointer flex items-center h-[38px] justify-center ml-2 "
    "rounded-default shadow-xs shrink-0 text-base-400 text-sm w-[38px] hover:text-base-700 "
    "dark:bg-base-900 dark:border-base-700 dark:text-base-500 dark:hover:text-base-200 "
    "focus:outline-2 focus:-outline-offset-2 focus:outline-primary-600"
)
CLASS_ATTR_RE = re.compile(
    r"\bclass=(?P<quote>[\"'])(?P<classes>.*?)(?P=quote)",
    re.DOTALL,
)
PY_CLASS_ATTR_RE = re.compile(r"""["']class["']\s*:\s*["'](?P<classes>[^"']*)["']""")
COMPONENT_BUTTON_CLASS_RE = re.compile(
    r"""\{%\s*component\s+["']unfold/components/button\.html["'][^%]*\bclass=["'][^"']*\b(?:h-|w-|min-w-|max-w-|px-|py-|p-)""",
    re.IGNORECASE,
)
INVENTORY_VERSION_RE = re.compile(r"^- Version: `(?P<version>[^`]+)`$", re.MULTILINE)
COLOR_TOKEN_RE = re.compile(
    r"^(?:"
    r"bg-(?:base|primary|red|green|blue|orange|amber|white|transparent)|"
    r"shadow-|"
    r"rounded-|"
    r"border-(?:base|primary|red|green|blue|orange|amber|white|transparent)|"
    r"text-(?:base|font|primary|red|green|blue|orange|amber|white|important|subtle)-"
    r")"
)
LAYOUT_TOKEN_RE = re.compile(
    r"^(?:"
    r"gap(?:-[xy])?-[\w\[\]/.-]+|"
    r"grid-cols-[\w\[\]/.-]+|"
    r"h-[\w\[\]/.-]+|"
    r"w-[\w\[\]/.-]+|"
    r"max-w-[\w\[\]/.-]+|"
    r"min-w-[\w\[\]/.-]+"
    r")$"
)
UTILITY_CLASS_RE = re.compile(
    r"^(?:"
    r"absolute|appearance-|backdrop-|block|bottom-|cursor-|dark:|flex|flex-|fixed|gap-|gap-x-|gap-y-|"
    r"grid|grid-|hidden|h-|inset-|items-|justify-|leading-|left-|list-|max-h-|max-w-|mb-|min-h-|"
    r"min-w-|mt-|mx-|my-|overflow-|p-|pb-|pl-|pr-|pt-|px-|py-|relative|right-|rounded-|shadow-|"
    r"space-x-|space-y-|sticky|text-|top-|truncate|w-|z-|tabular-nums$|aligned$"
    r")"
)


def _load_unfold_class_tokens() -> set[str]:
    spec = importlib.util.find_spec("unfold")
    if spec is None or not spec.submodule_search_locations:
        return set()

    tokens: set[str] = set()
    package_root = Path(next(iter(spec.submodule_search_locations)))
    for template in (package_root / "templates").rglob("*.html"):
        for match in CLASS_ATTR_RE.finditer(template.read_text(encoding="utf-8")):
            tokens.update(match.group("classes").split())
    return tokens


def _load_unfold_css() -> str:
    spec = importlib.util.find_spec("unfold")
    if spec is None or not spec.submodule_search_locations:
        return ""

    package_root = Path(next(iter(spec.submodule_search_locations)))
    css_path = package_root / "static/unfold/css/styles.css"
    if not css_path.exists():
        return ""
    return css_path.read_text(encoding="utf-8")


def _css_selector(class_name: str) -> str:
    return "." + class_name.replace(":", r"\:").replace("/", r"\/").replace("[", r"\[").replace("]", r"\]")


CANONICAL_UNFOLD_CLASSES = _load_unfold_class_tokens()
UNFOLD_CSS = _load_unfold_css()


@dataclass(frozen=True)
class Surface:
    id: str
    kind: str
    templates: tuple[Path, ...] = ()
    controllers: tuple[Path, ...] = ()
    projections: tuple[Path, ...] = ()
    urls: tuple[str, ...] = ()
    url_prefixes: tuple[str, ...] = ()
    replacement: str = ""
    exception_reason: str = ""
    requires_model_admin_view_mixin: bool = False
    required_extends: str = ""
    required_template_markers: tuple[str, ...] = ()
    required_controller_markers: tuple[str, ...] = ()


def _glob(pattern: str) -> tuple[Path, ...]:
    return tuple(sorted(ROOT.glob(pattern)))


def _paths(*paths: str) -> tuple[Path, ...]:
    return tuple(ROOT / path for path in paths)


CANONICAL_ADMIN_SURFACES: tuple[Surface, ...] = (
    Surface(
        id="admin-console-orders",
        kind="canonical-admin-unfold-page",
        templates=(ROOT / "shopman/backstage/templates/admin_console/orders",),
        controllers=(ROOT / "shopman/backstage/admin_console/orders.py",),
        projections=(ROOT / "shopman/backstage/projections/order_queue.py",),
        url_prefixes=("/admin/operacao/pedidos/",),
        requires_model_admin_view_mixin=True,
        required_extends="admin/base.html",
        required_template_markers=(
            'include "unfold/helpers/messages.html"',
            'include "unfold/helpers/tab_list.html"',
            'include "unfold/helpers/field.html"',
            'component "unfold/components/button.html"',
            'component "unfold/components/container.html"',
            'component "unfold/components/link.html"',
            'component "unfold/components/table.html"',
            'component "unfold/components/text.html"',
            'component "unfold/components/title.html"',
            'component "unfold/components/tracker.html"',
        ),
        required_controller_markers=(
            "UnfoldAdminTextareaWidget",
            "build_two_zone_queue",
            "build_order_card",
            "build_operator_order",
            "order_service.confirm_order",
            "order_service.advance_order",
            "order_service.reject_order",
        ),
    ),
    Surface(
        id="admin-console-kds",
        kind="canonical-admin-unfold-page",
        templates=(ROOT / "shopman/backstage/templates/admin_console/kds",),
        controllers=(ROOT / "shopman/backstage/admin_console/kds.py",),
        projections=(ROOT / "shopman/backstage/projections/kds.py",),
        url_prefixes=("/admin/operacao/kds/",),
        requires_model_admin_view_mixin=True,
        required_extends="admin/base.html",
        required_template_markers=(
            'include "unfold/helpers/messages.html"',
            'component "unfold/components/button.html"',
            'component "unfold/components/container.html"',
            'component "unfold/components/link.html"',
            'component "unfold/components/table.html"',
            'component "unfold/components/text.html"',
            'component "unfold/components/title.html"',
        ),
        required_controller_markers=(
            "build_kds_index",
            "build_kds_board",
            "kds_service.check_ticket_item",
            "kds_service.mark_ticket_done",
            "kds_service.expedition_action",
        ),
    ),
    Surface(
        id="admin-console-day-closing",
        kind="canonical-admin-unfold-page",
        templates=(ROOT / "shopman/backstage/templates/admin_console/closing",),
        controllers=(ROOT / "shopman/backstage/admin_console/closing.py",),
        projections=(ROOT / "shopman/backstage/projections/closing.py",),
        url_prefixes=("/admin/operacao/fechamento/",),
        requires_model_admin_view_mixin=True,
        required_extends="admin/base.html",
        required_template_markers=(
            'include "unfold/helpers/messages.html"',
            'component "unfold/components/button.html"',
            'component "unfold/components/container.html"',
            'component "unfold/components/table.html"',
            'component "unfold/components/text.html"',
            'component "unfold/components/title.html"',
        ),
        required_controller_markers=(
            "UnfoldAdminIntegerFieldWidget",
            "build_day_closing",
            "perform_day_closing",
        ),
    ),
    Surface(
        id="admin-console-production",
        kind="canonical-admin-unfold-page",
        templates=(
            ROOT / "shopman/backstage/templates/admin_console/production",
            ROOT / "shopman/backstage/templates/admin_console/unfold",
        ),
        controllers=(ROOT / "shopman/backstage/admin_console/production.py",),
        projections=(ROOT / "shopman/backstage/projections/production.py",),
        url_prefixes=("/admin/operacao/producao/",),
        requires_model_admin_view_mixin=True,
        required_extends="admin/base.html",
        required_template_markers=(
            'include "unfold/helpers/messages.html"',
            'include "unfold/helpers/tab_list.html"',
            'include "unfold/helpers/field.html"',
            'component "unfold/components/button.html"',
            'component "unfold/components/card.html"',
            'component "unfold/components/container.html"',
            'component "unfold/components/link.html"',
            'component "unfold/components/separator.html"',
            'component "unfold/components/table.html"',
            'component "unfold/components/text.html"',
            'component "unfold/components/title.html"',
            'component "unfold/components/tracker.html"',
        ),
        required_controller_markers=(
            "UnfoldAdminDecimalFieldWidget",
            "UnfoldAdminSelectWidget",
            "UnfoldAdminSingleDateWidget",
            "UnfoldAdminTextInputWidget",
            "render_production_surface",
            "build_production_console_context",
        ),
    ),
    Surface(
        id="admin-dashboard",
        kind="canonical-admin-unfold-page",
        templates=(ROOT / "shopman/shop/templates/admin/index.html",),
        controllers=(ROOT / "shopman/backstage/admin/dashboard.py",),
        projections=(ROOT / "shopman/backstage/projections/dashboard.py",),
        urls=("/admin/",),
        required_extends="admin/base.html",
    ),
    Surface(
        id="backstage-model-admin",
        kind="canonical-unfold-modeladmin",
        controllers=_glob("shopman/backstage/admin/*.py"),
        url_prefixes=("/admin/backstage/",),
    ),
    Surface(
        id="package-admin-unfold",
        kind="canonical-unfold-package-admin",
        templates=(
            *_glob("packages/*/shopman/*/templates/admin"),
            *_glob("packages/*/shopman/*/templates/*/admin"),
        ),
        controllers=(
            *_glob("packages/*/shopman/*/contrib/admin_unfold"),
        ),
        url_prefixes=(
            "/admin/craftsman/",
            "/admin/guestman/",
            "/admin/offerman/",
            "/admin/orderman/",
            "/admin/payman/",
            "/admin/refs/",
            "/admin/stockman/",
            "/admin/utils/",
        ),
    ),
)

RUNTIME_BACKSTAGE_SURFACES: tuple[Surface, ...] = (
    Surface(
        id="runtime-operator-shell",
        kind="registered-runtime-backstage",
        templates=_paths(
            "shopman/backstage/templates/gestor/404.html",
            "shopman/backstage/templates/gestor/base.html",
            "shopman/backstage/templates/gestor/partials/alerts_badge.html",
            "shopman/backstage/templates/gestor/partials/alerts_panel.html",
        ),
        replacement="Shared operator shell is registered runtime UI; management screens must use Admin/Unfold.",
    ),
    Surface(
        id="runtime-production-kds",
        kind="registered-runtime-backstage",
        templates=_paths(
            "shopman/backstage/templates/gestor/producao/kds.html",
            "shopman/backstage/templates/gestor/producao/partials/kds_cards.html",
            "shopman/backstage/templates/gestor/producao/partials/material_shortage.html",
            "shopman/backstage/templates/gestor/producao/partials/order_shortage.html",
        ),
        projections=(ROOT / "shopman/backstage/projections/production.py",),
        replacement="Production KDS is registered runtime UI; planning, reporting, and management screens must use Admin/Unfold.",
    ),
    Surface(
        id="runtime-pos",
        kind="registered-runtime-backstage",
        templates=(ROOT / "shopman/backstage/templates/pos",),
        projections=(ROOT / "shopman/backstage/projections/pos.py",),
        replacement="POS is registered runtime UI; management screens must use Admin/Unfold.",
    ),
    Surface(
        id="runtime-kds-customer",
        kind="registered-runtime-backstage",
        templates=(ROOT / "shopman/backstage/templates/runtime/kds_customer",),
        projections=(ROOT / "shopman/backstage/projections/kds.py",),
        replacement="Customer KDS board is registered runtime UI; KDS management screens must use Admin/Unfold.",
    ),
    Surface(
        id="runtime-kds-station",
        kind="registered-runtime-backstage",
        templates=(ROOT / "shopman/backstage/templates/runtime/kds_station",),
        projections=(ROOT / "shopman/backstage/projections/kds.py",),
        replacement="KDS station runtime is registered touch-first operator UI; KDS management screens must use Admin/Unfold.",
    ),
)

EXCEPTION_SURFACES: tuple[Surface, ...] = (
    Surface(
        id="storefront",
        kind="explicit-exception",
        templates=(ROOT / "shopman/storefront/templates", ROOT / "shopman/shop/templates/components"),
        exception_reason="Storefront is customer-facing and does not use the Admin shell.",
    ),
)

DEFAULT_TARGETS = [
    *(path for surface in CANONICAL_ADMIN_SURFACES for path in chain(surface.templates, surface.controllers)),
]

BLOCKING_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "raw-visible-input",
        re.compile(r"<input\b(?![^>]*\btype=[\"']hidden[\"'])", re.IGNORECASE),
        "Use a Django form field with an UnfoldAdmin*Widget instead of raw visible <input>.",
    ),
    (
        "raw-select",
        re.compile(r"<select\b", re.IGNORECASE),
        "Use forms.ChoiceField with UnfoldAdminSelectWidget instead of raw <select>.",
    ),
    (
        "raw-textarea",
        re.compile(r"<textarea\b", re.IGNORECASE),
        "Use forms.CharField with an Unfold textarea widget instead of raw <textarea>.",
    ),
    (
        "raw-button",
        re.compile(r"<button\b", re.IGNORECASE),
        'Use {% component "unfold/components/button.html" %} instead of raw <button>.',
    ),
    (
        "raw-table",
        re.compile(r"<table\b", re.IGNORECASE),
        'Use {% component "unfold/components/table.html" %} instead of raw <table>.',
    ),
    (
        "direct-tab-items-helper",
        re.compile(r"""include\s+["']unfold/helpers/tab_items\.html["']"""),
        'Use the complete "unfold/helpers/tab_list.html" helper for page tabs.',
    ),
    (
        "raw-material-icon",
        re.compile(r"""<span\b[^>]*class=["'][^"']*\bmaterial-symbols-outlined\b"""),
        'Use {% component "unfold/components/icon.html" %} instead of a raw Material Symbols span.',
    ),
    (
        "raw-heading",
        re.compile(r"<h[1-6]\b", re.IGNORECASE),
        'Use {% component "unfold/components/title.html" %} instead of a raw heading tag.',
    ),
    (
        "raw-label-badge",
        re.compile(
            r"""<span\b[^>]*class=["'][^"']*\brounded-default\b[^"']*\bbg-(?:base|primary|red|green|blue|orange|amber)-"""
        ),
        'Use {% include "unfold/helpers/label.html" %} instead of recreating a badge from classes.',
    ),
    (
        "component-button-sizing",
        COMPONENT_BUTTON_CLASS_RE,
        "Do not override Unfold button size/spacing classes; use the canonical button component size.",
    ),
    (
        "raw-form-label",
        re.compile(r"<label\b", re.IGNORECASE),
        "Use a Django form field rendered through unfold/helpers/field.html instead of raw <label>.",
    ),
    (
        "legacy-button-class",
        re.compile(r"""class=["'][^"']*\bbtn(?:\s|-)|class=["'][^"']*\bbutton\b""", re.IGNORECASE),
        'Use {% component "unfold/components/button.html" %} instead of legacy button classes.',
    ),
    (
        "legacy-admin-module",
        re.compile(r"""class=["'][^"']*\bmodule\b""", re.IGNORECASE),
        'Use {% component "unfold/components/card.html" %} instead of Django admin module shells.',
    ),
    (
        "canonical-admin-transitional-copy",
        re.compile(r"\b(?:[Pp]iloto|pilot|legacy_|tela antiga|UI atual)\b"),
        "Canonical Admin/Unfold surfaces must not present production UI as a pilot or legacy fallback.",
    ),
    (
        "raw-modal-overlay",
        re.compile(r'class="[^"]*\bfixed\b[^"]*\binset-0\b[^"]*\bz-\[?1000\]?', re.IGNORECASE),
        "Use Unfold dialog actions/BaseDialogForm where possible; custom modal overlays require authorization.",
    ),
    (
        "raw-collapsible",
        re.compile(r"</?(details|summary)\b", re.IGNORECASE),
        "Use Unfold sections/changelist patterns where possible; custom collapsibles require authorization.",
    ),
    (
        "raw-visual-shell",
        re.compile(
            r'class="[^"]*(?:\bfixed\b[^"]*\binset-0\b|\bborder\b[^"]*\brounded-[\w/-]+|\bbg-[\w/-]+[^"]*\brounded-[\w/-]+|\bshadow-[\w/-]+)',
            re.IGNORECASE,
        ),
        "Visual shell classes should come from Unfold components/helpers, not hand-built HTML.",
    ),
)

TEMPLATE_ONLY_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "direct-component-include",
        re.compile(r"""\{%\s*include\s+["']unfold/components/"""),
        'Use the documented {% component "unfold/components/..." %} tag instead of including components directly.',
    ),
    (
        "raw-anchor",
        re.compile(r"<a\b", re.IGNORECASE),
        'Use {% component "unfold/components/link.html" %} or button.html instead of raw <a>.',
    ),
    (
        "raw-paragraph",
        re.compile(r"<p\b", re.IGNORECASE),
        'Use {% component "unfold/components/text.html" %} instead of raw <p> copy.',
    ),
)

NON_WAIVABLE_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "inline-style",
        re.compile(r"\bstyle=", re.IGNORECASE),
        "Inline styles bypass Unfold design tokens and are forbidden even in approved custom UI.",
    ),
)

STRICT_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = ()

ALLOW_RE = re.compile(
    r"unfold-canonical:\s*allow\s+([\w-]+)\s+--\s*"
    r"authorized-by=([^;]+);\s*authorization-ref=([^;]+);\s*reason=(.+)"
)
LOOSE_ALLOW_RE = re.compile(r"unfold-canonical:\s*allow\b")


@dataclass(frozen=True)
class Violation:
    path: Path
    line_no: int
    rule: str
    message: str
    line: str

    def render(self) -> str:
        try:
            rel = self.path.relative_to(ROOT)
        except ValueError:
            rel = self.path
        return f"{rel}:{self.line_no}: {self.rule}: {self.message}\n    {self.line.strip()}"


def _is_allowed(lines: list[str], index: int, rule: str) -> bool:
    candidates = [lines[index]]
    if index > 0:
        candidates.append(lines[index - 1])
    for line in candidates:
        match = ALLOW_RE.search(line)
        if (
            match
            and match.group(1) == rule
            and _valid_authorization(match.group(2), match.group(3), match.group(4))
        ):
            return True
    return False


def _valid_authorization(authorized_by: str, authorization_ref: str, reason: str) -> bool:
    authorized_by = authorized_by.strip().lower()
    authorization_ref = authorization_ref.strip().lower()
    reason = reason.strip()
    if authorized_by in {"", "self", "codex", "agent", "pending", "todo", "tbd"}:
        return False
    if authorization_ref in {"", "self", "pending", "todo", "tbd"}:
        return False
    return len(reason) >= 20


def scan_malformed_waivers(path: Path) -> list[Violation]:
    lines = path.read_text(encoding="utf-8").splitlines()
    violations: list[Violation] = []
    for index, line in enumerate(lines):
        if LOOSE_ALLOW_RE.search(line) and not ALLOW_RE.search(line):
            violations.append(
                Violation(
                    path,
                    index + 1,
                    "malformed-waiver",
                    "Custom Unfold waivers must include authorized-by, authorization-ref, and reason.",
                    line,
                )
            )
    return violations


def scan_file(path: Path, *, strict: bool) -> list[Violation]:
    patterns = [
        *BLOCKING_PATTERNS,
        *(TEMPLATE_ONLY_PATTERNS if path.suffix == ".html" else ()),
        *(STRICT_PATTERNS if strict else ()),
    ]
    lines = path.read_text(encoding="utf-8").splitlines()
    violations = scan_malformed_waivers(path)
    for index, line in enumerate(lines):
        for rule, pattern, message in NON_WAIVABLE_PATTERNS:
            if pattern.search(line):
                violations.append(Violation(path, index + 1, rule, message, line))
        line_rules: set[str] = set()
        for rule, pattern, message in patterns:
            if rule == "raw-visual-shell" and "{% component " in line:
                continue
            if rule == "raw-visual-shell" and {"raw-modal-overlay", "raw-collapsible"} & line_rules:
                continue
            if pattern.search(line):
                if _is_approved_modal_shell(path, line, rule):
                    line_rules.add(rule)
                    continue
                if _is_approved_row_action_shell(path, line, rule):
                    line_rules.add(rule)
                    continue
                if rule == "raw-modal-overlay" and path.resolve() != APPROVED_MODAL_TEMPLATE:
                    violations.append(
                        Violation(
                            path,
                            index + 1,
                            "raw-modal-overlay-location",
                            "Custom modal overlays must use admin_console/unfold/modal.html.",
                            line,
                        )
                    )
                    line_rules.add(rule)
                    continue
                if _is_allowed(lines, index, rule):
                    line_rules.add(rule)
                    continue
                violations.append(Violation(path, index + 1, rule, message, line))
                line_rules.add(rule)
        violations.extend(scan_design_token_classes(path, index, line))
    violations.extend(scan_structural_unfold_usage(path, lines))
    return violations


def scan_structural_unfold_usage(path: Path, lines: list[str]) -> list[Violation]:
    violations: list[Violation] = []
    text = "\n".join(lines)
    if "dialog={" in text and "BaseDialogForm" not in text:
        for index, line in enumerate(lines):
            if "dialog={" not in line:
                continue
            violations.append(
                Violation(
                    path,
                    index + 1,
                    "dialog-action-without-basedialogform",
                    "Official Unfold dialog actions must be backed by unfold.forms.BaseDialogForm.",
                    line,
                )
            )
            break

    for index, line in enumerate(lines):
        if 'component "unfold/components/table.html"' not in line or "card_included=1" not in line:
            continue
        card_start = max(
            (
                candidate
                for candidate in range(index - 1, -1, -1)
                if 'component "unfold/components/card.html"' in lines[candidate]
            ),
            default=max(0, index - 12),
        )
        card_prefix = "\n".join(lines[card_start:index])
        if 'component "unfold/components/text.html"' in card_prefix:
            violations.append(
                Violation(
                    path,
                    index + 1,
                    "card-included-table-body-prefix",
                    "Unfold table with card_included=1 uses negative margins and must be the first card body content; put copy in the card action/title instead.",
                    line,
                )
            )
    return violations


def _is_approved_modal_shell(path: Path, line: str, rule: str) -> bool:
    if path.resolve() != APPROVED_MODAL_TEMPLATE:
        return False
    if rule == "raw-modal-overlay":
        return APPROVED_MODAL_OVERLAY_CLASS in line
    if rule == "raw-visual-shell":
        return APPROVED_MODAL_PANEL_CLASS in line
    return False


def _is_approved_row_action_shell(path: Path, line: str, rule: str) -> bool:
    if path.resolve() != APPROVED_ROW_ACTION_TEMPLATE:
        return False
    if rule in {"raw-button", "raw-visual-shell"}:
        return APPROVED_ROW_ACTION_CLASS in line
    return False


def scan_approved_custom_partials() -> list[Violation]:
    violations: list[Violation] = []
    modal = APPROVED_MODAL_TEMPLATE
    if modal.exists():
        text = modal.read_text(encoding="utf-8")
        required = [
            "unfold-canonical: allow raw-modal-overlay",
            APPROVED_MODAL_OVERLAY_CLASS,
            APPROVED_MODAL_PANEL_CLASS,
            'component "unfold/components/card.html"',
            'component "unfold/components/button.html"',
            'include "unfold/helpers/field.html"',
            'role="dialog"',
            'aria-modal="true"',
        ]
        for marker in required:
            if marker not in text:
                violations.append(
                    Violation(
                        modal,
                        1,
                        "invalid-approved-modal",
                        f"Approved custom modal wrapper is missing `{marker}`.",
                        "",
                    )
                )
    row_action = APPROVED_ROW_ACTION_TEMPLATE
    if row_action.exists():
        text = row_action.read_text(encoding="utf-8")
        required = [
            "unfold-canonical: allow raw-button",
            APPROVED_ROW_ACTION_CLASS,
            "type=\"{% if submit %}submit{% else %}button{% endif %}\"",
            "aria-label",
            'component "unfold/components/icon.html"',
        ]
        for marker in required:
            if marker not in text:
                violations.append(
                    Violation(
                        row_action,
                        1,
                        "invalid-approved-row-action",
                        f"Approved row action wrapper is missing `{marker}`.",
                        "",
                    )
                )
    return violations


def scan_design_token_classes(path: Path, index: int, line: str) -> list[Violation]:
    violations: list[Violation] = []
    if _is_approved_custom_shell_line(path, line):
        return violations
    class_groups = [
        *(match.group("classes") for match in CLASS_ATTR_RE.finditer(line)),
        *(match.group("classes") for match in PY_CLASS_ATTR_RE.finditer(line)),
    ]
    for classes in class_groups:
        for class_name in classes.split():
            class_base = class_name.split(":")[-1].rstrip("!")
            if "[" not in class_name:
                if not COLOR_TOKEN_RE.match(class_base):
                    if not LAYOUT_TOKEN_RE.match(class_base):
                        if UTILITY_CLASS_RE.match(class_name) or UTILITY_CLASS_RE.match(class_base):
                            violations.extend(
                                _css_class_violation(
                                    path,
                                    index,
                                    line,
                                    class_name,
                                    rule="unknown-unfold-css-class",
                                    message=f"`{class_name}` is not present in compiled Unfold CSS.",
                                )
                            )
                        continue
                    if _class_exists_in_unfold_css(class_name, class_base):
                        continue
                    violations.extend(
                        _css_class_violation(
                            path,
                            index,
                            line,
                            class_name,
                            rule="noncanonical-layout-class",
                            message=f"`{class_name}` is not present in compiled Unfold CSS.",
                        )
                    )
                    continue
                if class_name in CANONICAL_UNFOLD_CLASSES or class_base in CANONICAL_UNFOLD_CLASSES:
                    continue
                violations.append(
                    Violation(
                        path,
                        index + 1,
                        "noncanonical-design-token",
                        f"`{class_name}` is not present in official Unfold templates.",
                        line,
                    )
                )
                continue
            if class_name in CANONICAL_UNFOLD_CLASSES or class_base in CANONICAL_UNFOLD_CLASSES:
                continue
            violations.append(
                Violation(
                    path,
                    index + 1,
                    "noncanonical-arbitrary-class",
                    f"`{class_name}` is forbidden unless the exact class exists in Unfold templates.",
                    line,
                )
            )
    return violations


def _is_approved_custom_shell_line(path: Path, line: str) -> bool:
    resolved = path.resolve()
    if resolved == APPROVED_MODAL_TEMPLATE:
        return APPROVED_MODAL_OVERLAY_CLASS in line or APPROVED_MODAL_PANEL_CLASS in line
    if resolved == APPROVED_ROW_ACTION_TEMPLATE:
        return APPROVED_ROW_ACTION_CLASS in line
    return False


def _class_exists_in_unfold_css(class_name: str, class_base: str) -> bool:
    return _css_selector(class_name) in UNFOLD_CSS or _css_selector(class_base) in UNFOLD_CSS


def _css_class_violation(
    path: Path,
    index: int,
    line: str,
    class_name: str,
    *,
    rule: str,
    message: str,
) -> list[Violation]:
    class_base = class_name.split(":")[-1].rstrip("!")
    if _class_exists_in_unfold_css(class_name, class_base):
        return []
    return [Violation(path, index + 1, rule, message, line)]


def iter_templates(targets: list[Path]) -> list[Path]:
    files: list[Path] = []
    for target in targets:
        target = target if target.is_absolute() else ROOT / target
        if target.is_file():
            files.append(target)
        else:
            files.extend(sorted(path for path in target.rglob("*") if path.suffix in {".html", ".py"}))
    return [path for path in files if "__pycache__" not in path.parts]


def targets_for_surfaces(surfaces: tuple[Surface, ...]) -> list[Path]:
    return [
        path
        for surface in surfaces
        for path in chain(surface.templates, surface.controllers)
    ]


def _normalize_url(value: str) -> str:
    path = urlparse(value).path.strip()
    if not path:
        return "/"
    if not path.startswith("/"):
        path = f"/{path}"
    if not path.endswith("/"):
        path = f"{path}/"
    return path


def surfaces_for_url(value: str) -> tuple[Surface, ...]:
    path = _normalize_url(value)
    surfaces: list[Surface] = []
    for surface in CANONICAL_ADMIN_SURFACES:
        if path in surface.urls:
            surfaces.append(surface)
            continue
        if any(path.startswith(prefix) for prefix in surface.url_prefixes):
            surfaces.append(surface)
    return tuple(surfaces)


def render_url_scopes() -> str:
    lines = ["Registered Admin URL scopes:"]
    for surface in CANONICAL_ADMIN_SURFACES:
        for url in surface.urls:
            lines.append(f"- {url} -> {surface.id}")
        for prefix in surface.url_prefixes:
            lines.append(f"- {prefix}* -> {surface.id}")
    return "\n".join(lines)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _existing_template_files(paths: tuple[Path, ...]) -> set[Path]:
    files: set[Path] = set()
    for path in paths:
        if path.is_file() and path.suffix == ".html":
            files.add(path.resolve())
        elif path.is_dir():
            files.update(candidate.resolve() for candidate in path.rglob("*.html"))
    return files


def _known_backstage_templates() -> set[Path]:
    files: set[Path] = set()
    for surface in CANONICAL_ADMIN_SURFACES:
        files.update(_existing_template_files(surface.templates))
    for surface in RUNTIME_BACKSTAGE_SURFACES:
        files.update(_existing_template_files(surface.templates))
    return files


def _exception_template_dirs() -> tuple[Path, ...]:
    return tuple(path for surface in EXCEPTION_SURFACES for path in surface.templates if path.is_dir())


def _registered_projection_files() -> set[Path]:
    return {
        path.resolve()
        for surface in (*CANONICAL_ADMIN_SURFACES, *RUNTIME_BACKSTAGE_SURFACES, *EXCEPTION_SURFACES)
        for path in surface.projections
        if path.exists()
    }


def _projection_module(path: Path) -> str:
    rel = path.resolve().relative_to(ROOT).with_suffix("")
    return ".".join(rel.parts)


def scan_surface_registry(
    extra_backstage_templates: tuple[Path, ...] = (),
    *,
    surfaces: tuple[Surface, ...] | None = None,
    enforce_global_contract: bool = True,
) -> list[Violation]:
    """Ensure backstage UI growth is routed through registered Admin/Unfold surfaces."""
    violations: list[Violation] = []
    surfaces_to_check = surfaces or CANONICAL_ADMIN_SURFACES

    if enforce_global_contract:
        known_templates = _known_backstage_templates()
        exception_dirs = _exception_template_dirs()
        backstage_templates = (
            tuple(sorted(BACKSTAGE_TEMPLATES.rglob("*.html"))) if BACKSTAGE_TEMPLATES.exists() else ()
        )

        for path in (*backstage_templates, *extra_backstage_templates):
            resolved = path.resolve()
            if any(_is_relative_to(resolved, directory) for directory in exception_dirs):
                continue
            if resolved in known_templates:
                continue
            violations.append(
                Violation(
                    path,
                    1,
                    "unregistered-backstage-surface",
                    "Backstage templates must be canonical Admin/Unfold or an explicitly registered runtime surface.",
                    "",
                )
            )

        registered_projections = _registered_projection_files()
        for path in sorted(BACKSTAGE_PROJECTIONS.glob("*.py")):
            if path.name in {"__init__.py", "_helpers.py"}:
                continue
            if path.resolve() in registered_projections:
                continue
            violations.append(
                Violation(
                    path,
                    1,
                    "unregistered-backstage-projection",
                    "Backstage projection modules must be tied to a registered surface or exception.",
                    "",
                )
            )

    for surface in surfaces_to_check:
        surface_templates = _existing_template_files(surface.templates)
        if surface.required_extends:
            for template in surface_templates:
                extends = _template_extends(template)
                if extends and extends != surface.required_extends:
                    violations.append(
                        Violation(
                            template,
                            1,
                            "admin-page-noncanonical-base",
                            f"Canonical Admin pages must extend `{surface.required_extends}` to match official Unfold pages and demo templates.",
                            "",
                        )
                    )

        if surface.required_template_markers:
            combined_template_text = "\n".join(
                template.read_text(encoding="utf-8") for template in surface_templates
            )
            for marker in surface.required_template_markers:
                if marker not in combined_template_text:
                    violations.append(
                        Violation(
                            next(iter(surface_templates), ROOT),
                            1,
                            "admin-surface-missing-unfold-primitive",
                            f"Canonical Admin surface `{surface.id}` must compose official Unfold primitive `{marker}`.",
                            "",
                        )
                    )

        for controller in surface.controllers:
            if controller.is_dir() or not controller.exists() or not surface.projections:
                continue
            text = controller.read_text(encoding="utf-8")
            for marker in surface.required_controller_markers:
                if marker not in text:
                    violations.append(
                        Violation(
                            controller,
                            1,
                            "admin-surface-missing-unfold-controller-primitive",
                            f"Canonical Admin surface `{surface.id}` must use `{marker}` for its projection-backed Admin UX.",
                            "",
                        )
                    )
            if surface.requires_model_admin_view_mixin:
                required_markers = (
                    "UnfoldModelAdminViewMixin",
                    "TemplateView",
                    "permission_required",
                    "title =",
                    ".as_view(model_admin=",
                )
                for marker in required_markers:
                    if marker not in text:
                        violations.append(
                            Violation(
                                controller,
                                1,
                                "admin-page-missing-official-unfold-view-contract",
                                f"Canonical Admin page `{surface.id}` must use the official UnfoldModelAdminViewMixin custom-page contract; missing `{marker}`.",
                                "",
                            )
                        )
            for projection in surface.projections:
                module = _projection_module(projection)
                if projection.exists() and module not in text:
                    violations.append(
                        Violation(
                            controller,
                            1,
                            "admin-surface-missing-projection",
                            f"Canonical Admin surface `{surface.id}` must consume `{module}` instead of ad-hoc template context.",
                            "",
                        )
                    )
    return violations


def scan_unfold_installation() -> list[Violation]:
    violations: list[Violation] = []
    try:
        installed_version = importlib.metadata.version("django-unfold")
    except importlib.metadata.PackageNotFoundError:
        installed_version = ""

    if not (installed_version and CANONICAL_UNFOLD_CLASSES and UNFOLD_CSS):
        violations.append(
            Violation(
                ROOT / "pyproject.toml",
                1,
                "unfold-package-unavailable",
                "The canonical gate requires the installed django-unfold package, templates, and compiled CSS to validate tokens.",
                "",
            )
        )
        return violations

    inventory_version = _inventory_version()
    if not inventory_version:
        violations.append(
            Violation(
                INVENTORY,
                1,
                "unfold-inventory-missing-version",
                "The official Unfold inventory must be generated before the canonical gate can run.",
                "",
            )
        )
    elif inventory_version != installed_version:
        violations.append(
            Violation(
                INVENTORY,
                1,
                "unfold-inventory-version-drift",
                f"Inventory version `{inventory_version}` does not match installed django-unfold `{installed_version}`; update the package and rerun scripts/snapshot_unfold_reference.py.",
                "",
            )
        )

    spec = importlib.util.find_spec("unfold")
    package_root = Path(next(iter(spec.submodule_search_locations))) if spec and spec.submodule_search_locations else None
    required_components = (
        "templates/unfold/components/button.html",
        "templates/unfold/components/card.html",
        "templates/unfold/components/container.html",
        "templates/unfold/components/link.html",
        "templates/unfold/components/table.html",
        "templates/unfold/components/text.html",
        "templates/unfold/components/title.html",
        "templates/unfold/components/chart/bar.html",
        "templates/unfold/components/chart/line.html",
        "templates/unfold/components/chart/cohort.html",
    )
    if package_root is not None:
        for component in required_components:
            if not (package_root / component).exists():
                violations.append(
                    Violation(
                        ROOT / "pyproject.toml",
                        1,
                        "unfold-official-component-missing",
                        f"Installed django-unfold is missing official component `{component}` required by the canonical gate.",
                        "",
                    )
                )

    required_symbols = (
        ("views.py", "class UnfoldModelAdminViewMixin"),
        ("forms.py", "class BaseDialogForm"),
    )
    for module_file, marker in required_symbols:
        source = (package_root / module_file) if package_root is not None else None
        if source is None or not source.exists():
            violations.append(
                Violation(
                    ROOT / "pyproject.toml",
                    1,
                    "unfold-official-symbol-unavailable",
                    f"Installed django-unfold does not ship `{module_file}` required by the canonical gate.",
                    "",
                )
            )
            continue
        if marker not in source.read_text(encoding="utf-8"):
            violations.append(
                Violation(
                    ROOT / "pyproject.toml",
                    1,
                    "unfold-official-symbol-missing",
                    f"Installed django-unfold does not expose `{marker}` required by the canonical gate.",
                    "",
                )
            )

    return violations


def _inventory_version() -> str:
    if not INVENTORY.exists():
        return ""
    match = INVENTORY_VERSION_RE.search(INVENTORY.read_text(encoding="utf-8"))
    return match.group("version") if match else ""


def _template_extends(template: Path) -> str:
    match = re.search(
        r"""\{%\s*extends\s+["'](?P<template>[^"']+)["']\s*%\}""",
        template.read_text(encoding="utf-8"),
    )
    return match.group("template") if match else ""


def render_surface_registry() -> str:
    lines = ["Registered Unfold/backstage surfaces:"]
    for surface in (*CANONICAL_ADMIN_SURFACES, *RUNTIME_BACKSTAGE_SURFACES, *EXCEPTION_SURFACES):
        lines.append(f"- {surface.id} [{surface.kind}]")
        if surface.urls or surface.url_prefixes:
            urls = ", ".join((*surface.urls, *(f"{prefix}*" for prefix in surface.url_prefixes)))
            lines.append(f"  urls: {urls}")
        if surface.projections:
            projections = ", ".join(str(path.relative_to(ROOT)) for path in surface.projections)
            lines.append(f"  projections: {projections}")
        if surface.replacement:
            lines.append(f"  replacement: {surface.replacement}")
        if surface.exception_reason:
            lines.append(f"  exception: {surface.exception_reason}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="*", type=Path)
    parser.add_argument("--strict", action="store_true", help="also flag visual-shell drift")
    parser.add_argument("--maturity", action="store_true", help="alias for --strict before declaring a page mature")
    parser.add_argument("--surfaces", action="store_true", help="print the registered Admin/backstage surface contract")
    parser.add_argument("--url", help="scope validation to a registered relative Admin URL, for example /admin/operacao/producao/")
    parser.add_argument(
        "--skip-surface-contract",
        action="store_true",
        help="scan only file contents; do not enforce the backstage surface registry",
    )
    args = parser.parse_args(argv)

    if args.surfaces:
        print(render_surface_registry())
        return 0

    scoped_surfaces: tuple[Surface, ...] = ()
    if args.url:
        scoped_surfaces = surfaces_for_url(args.url)
        if not scoped_surfaces:
            print(
                f"Unknown Admin URL scope `{args.url}`.\n\n{render_url_scopes()}",
            )
            return 2

    targets = args.targets or (targets_for_surfaces(scoped_surfaces) if scoped_surfaces else DEFAULT_TARGETS)
    violations: list[Violation] = []
    violations.extend(scan_unfold_installation())
    for template in iter_templates(targets):
        violations.extend(scan_file(template, strict=args.strict or args.maturity))
    if not args.targets and not args.skip_surface_contract:
        violations.extend(
            scan_surface_registry(
                surfaces=scoped_surfaces or None,
                enforce_global_contract=not scoped_surfaces,
            )
        )
    violations.extend(scan_approved_custom_partials())

    if violations:
        print("Non-canonical Unfold Admin template usage detected:\n")
        print("\n".join(violation.render() for violation in violations))
        print(
            "\nUse official Unfold components/helpers/widgets, or add a narrow "
            "`unfold-canonical: allow <rule> -- authorized-by=<user>; "
            "authorization-ref=<link-or-doc>; reason=<why no Unfold primitive fits>` "
            "waiver only after explicit user authorization."
        )
        return 1

    print("Unfold canonical template check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
