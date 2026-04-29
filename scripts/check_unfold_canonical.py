#!/usr/bin/env python
"""Guard Admin templates against non-canonical Django Unfold controls."""

from __future__ import annotations

import argparse
import importlib.util
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = [
    ROOT / "shopman/backstage/templates/admin_console",
    ROOT / "shopman/backstage/admin_console",
]
APPROVED_MODAL_TEMPLATE = ROOT / "shopman/backstage/templates/admin_console/unfold/modal.html"
APPROVED_MODAL_OVERLAY_CLASS = "backdrop-blur-xs bg-base-900/80 flex flex-col fixed inset-0 p-4 lg:p-32 z-[1000]"
APPROVED_MODAL_PANEL_CLASS = (
    "bg-white flex flex-col max-w-sm min-h-0 mx-auto overflow-hidden rounded-default shadow-lg "
    "w-full dark:bg-base-800"
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
)

NON_WAIVABLE_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "inline-style",
        re.compile(r"\bstyle=", re.IGNORECASE),
        "Inline styles bypass Unfold design tokens and are forbidden even in approved custom UI.",
    ),
)

STRICT_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
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
        rel = self.path.relative_to(ROOT)
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
    patterns = [*BLOCKING_PATTERNS, *(STRICT_PATTERNS if strict else ())]
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
    return violations


def _is_approved_modal_shell(path: Path, line: str, rule: str) -> bool:
    if path.resolve() != APPROVED_MODAL_TEMPLATE:
        return False
    if rule == "raw-modal-overlay":
        return APPROVED_MODAL_OVERLAY_CLASS in line
    if rule == "raw-visual-shell":
        return APPROVED_MODAL_PANEL_CLASS in line
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
    return violations


def scan_design_token_classes(path: Path, index: int, line: str) -> list[Violation]:
    violations: list[Violation] = []
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="*", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--strict", action="store_true", help="also flag visual-shell drift")
    parser.add_argument("--maturity", action="store_true", help="alias for --strict before declaring a page mature")
    args = parser.parse_args(argv)

    violations: list[Violation] = []
    for template in iter_templates(args.targets):
        violations.extend(scan_file(template, strict=args.strict or args.maturity))
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
