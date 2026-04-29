#!/usr/bin/env python
"""Write a local inventory of the installed Django Unfold primitives."""

from __future__ import annotations

import importlib.metadata
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/reference/unfold_canonical_inventory.md"

OFFICIAL_DOCS = [
    ("Documentation index", "https://unfoldadmin.com/docs/"),
    ("Components introduction", "https://unfoldadmin.com/docs/components/introduction/"),
    ("Component class", "https://unfoldadmin.com/docs/components/component/"),
    ("Card", "https://unfoldadmin.com/docs/components/card/"),
    ("Table", "https://unfoldadmin.com/docs/components/table/"),
    ("Chart", "https://unfoldadmin.com/docs/components/chart/"),
    ("Button", "https://unfoldadmin.com/docs/components/button/"),
    ("Progress", "https://unfoldadmin.com/docs/components/progress/"),
    ("Layer", "https://unfoldadmin.com/docs/components/layer/"),
    ("Custom pages", "https://unfoldadmin.com/docs/configuration/custom-pages/"),
    ("ModelAdmin options", "https://unfoldadmin.com/docs/configuration/modeladmin/"),
    ("Sections / expandable rows", "https://unfoldadmin.com/docs/configuration/sections/"),
    ("Filters", "https://unfoldadmin.com/docs/filters/introduction/"),
    ("Horizontal layout filter", "https://unfoldadmin.com/docs/filters/horizontal-layout/"),
    ("Actions with dialog", "https://unfoldadmin.com/docs/actions/dialog-actions/"),
    ("Changelist row actions", "https://unfoldadmin.com/docs/actions/changelist-row-actions/"),
    ("Action with form example", "https://unfoldadmin.com/docs/actions/action-form-example/"),
    ("Dynamic tabs", "https://unfoldadmin.com/docs/tabs/dynamic/"),
    ("Display decorator", "https://unfoldadmin.com/docs/decorators/display/"),
    ("Action decorator", "https://unfoldadmin.com/docs/decorators/action/"),
    ("Official demo repository", "https://github.com/unfoldadmin/formula"),
    ("Official Unfold repository", "https://github.com/unfoldadmin/django-unfold"),
]


def main() -> int:
    spec = importlib.util.find_spec("unfold")
    if spec is None or not spec.submodule_search_locations:
        raise SystemExit("django-unfold is not importable")

    package_root = Path(next(iter(spec.submodule_search_locations)))
    version = importlib.metadata.version("django-unfold")

    components = _names(package_root / "templates/unfold/components")
    helpers = _names(package_root / "templates/unfold/helpers")
    crispy_layouts = _names(package_root / "templates/unfold_crispy/layout")
    crispy_templates = _names(package_root / "templates/unfold_crispy")
    widgets = _widget_names(package_root / "widgets.py")
    forms = _form_names(package_root / "forms.py")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        "\n".join(
            [
                "# Unfold Canonical Inventory",
                "",
                "Generated from the installed `django-unfold` package. Do not hand-edit; run:",
                "",
                "```bash",
                "python scripts/snapshot_unfold_reference.py",
                "```",
                "",
                f"- Version: `{version}`",
                f"- Package root: `{package_root}`",
                "",
                "## Official References",
                "",
                *_bullets(f"[{label}]({url})" for label, url in OFFICIAL_DOCS),
                "",
                "## Components",
                "",
                *_bullets(f"`unfold/components/{name}`" for name in components),
                "",
                "## Helpers",
                "",
                *_bullets(f"`unfold/helpers/{name}`" for name in helpers),
                "",
                "## Crispy Form Templates",
                "",
                *_bullets(f"`unfold_crispy/{name}`" for name in crispy_templates),
                "",
                "## Crispy Layout Templates",
                "",
                *_bullets(f"`unfold_crispy/layout/{name}`" for name in crispy_layouts),
                "",
                "## Widgets",
                "",
                *_bullets(f"`unfold.widgets.{name}`" for name in widgets),
                "",
                "## Forms",
                "",
                *_bullets(f"`unfold.forms.{name}`" for name in forms),
                "",
                "## Usage Rule",
                "",
                "Use this inventory as the first local lookup before creating custom Admin UI. "
                "If a component/helper/widget/form exists here, use that public primitive before copying classes. "
                "For behavior semantics, consult the official docs or repositories linked above.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    return 0


def _names(path: Path) -> list[str]:
    if not path.exists():
        return []
    return sorted(item.name for item in path.glob("*.html"))


def _widget_names(path: Path) -> list[str]:
    if not path.exists():
        return []
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("class Unfold") and "(" in stripped:
            names.append(stripped.split("(", 1)[0].removeprefix("class ").strip())
    return sorted(names)


def _form_names(path: Path) -> list[str]:
    if not path.exists():
        return []
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("class ") and "(" in stripped:
            name = stripped.split("(", 1)[0].removeprefix("class ").strip()
            if name.endswith("Form") or "Dialog" in name:
                names.append(name)
    return sorted(names)


def _bullets(items) -> list[str]:
    values = list(items)
    if not values:
        return ["- None found"]
    return [f"- {item}" for item in values]


if __name__ == "__main__":
    raise SystemExit(main())
