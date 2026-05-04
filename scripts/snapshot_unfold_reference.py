#!/usr/bin/env python
"""Write a local inventory of the installed Django Unfold primitives."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/reference/unfold_canonical_inventory.md"

OFFICIAL_DOCS = [
    ("Documentation index", "https://unfoldadmin.com/docs/"),
    ("Quickstart", "https://unfoldadmin.com/docs/installation/quickstart/"),
    ("User & group models", "https://unfoldadmin.com/docs/installation/auth/"),
    ("Settings options", "https://unfoldadmin.com/docs/configuration/settings/"),
    ("Site dropdown", "https://unfoldadmin.com/docs/configuration/site-dropdown/"),
    ("Components introduction", "https://unfoldadmin.com/docs/components/introduction/"),
    ("Component class", "https://unfoldadmin.com/docs/components/component-class/"),
    ("Cohort", "https://unfoldadmin.com/docs/components/cohort/"),
    ("Tracker", "https://unfoldadmin.com/docs/components/tracker/"),
    ("Card", "https://unfoldadmin.com/docs/components/card/"),
    ("Table", "https://unfoldadmin.com/docs/components/table/"),
    ("Chart", "https://unfoldadmin.com/docs/components/chart/"),
    ("Link", "https://unfoldadmin.com/docs/components/link/"),
    ("Button", "https://unfoldadmin.com/docs/components/button/"),
    ("Progress", "https://unfoldadmin.com/docs/components/progress/"),
    ("Layer", "https://unfoldadmin.com/docs/components/layer/"),
    ("Custom pages", "https://unfoldadmin.com/docs/configuration/custom-pages/"),
    ("ModelAdmin options", "https://unfoldadmin.com/docs/configuration/modeladmin/"),
    ("Conditional fields", "https://unfoldadmin.com/docs/configuration/conditional-fields/"),
    ("Command", "https://unfoldadmin.com/docs/configuration/command/"),
    ("Paginator", "https://unfoldadmin.com/docs/configuration/paginator/"),
    ("Crispy Forms", "https://unfoldadmin.com/docs/configuration/crispy-forms/"),
    ("Sections / expandable rows", "https://unfoldadmin.com/docs/configuration/sections/"),
    ("Sortable changelist", "https://unfoldadmin.com/docs/configuration/sortable-changelist/"),
    ("Dashboard", "https://unfoldadmin.com/docs/configuration/dashboard/"),
    ("Custom sites", "https://unfoldadmin.com/docs/configuration/custom-sites/"),
    ("Multi-language", "https://unfoldadmin.com/docs/configuration/multi-language/"),
    ("Datasets", "https://unfoldadmin.com/docs/configuration/datasets/"),
    ("Filters", "https://unfoldadmin.com/docs/filters/introduction/"),
    ("Text filter", "https://unfoldadmin.com/docs/filters/text/"),
    ("Datetime filter", "https://unfoldadmin.com/docs/filters/datetime/"),
    ("Dropdown filter", "https://unfoldadmin.com/docs/filters/dropdown/"),
    ("Numeric filter", "https://unfoldadmin.com/docs/filters/numeric/"),
    ("Horizontal layout filter", "https://unfoldadmin.com/docs/filters/horizontal/"),
    ("Autocomplete filter", "https://unfoldadmin.com/docs/filters/autocomplete/"),
    ("Checkbox and radio filters", "https://unfoldadmin.com/docs/filters/checkbox-radio/"),
    ("Actions introduction", "https://unfoldadmin.com/docs/actions/introduction/"),
    ("Actions with dialog", "https://unfoldadmin.com/docs/actions/dialog-actions/"),
    ("Changelist actions", "https://unfoldadmin.com/docs/actions/changelist/"),
    ("Changelist row actions", "https://unfoldadmin.com/docs/actions/changelist-row/"),
    ("Changeform actions", "https://unfoldadmin.com/docs/actions/changeform/"),
    ("Changeform submitline actions", "https://unfoldadmin.com/docs/actions/changeform-submitline/"),
    ("Dropdown action", "https://unfoldadmin.com/docs/actions/dropdown-actions/"),
    ("Action with form example", "https://unfoldadmin.com/docs/actions/action-form-example/"),
    ("Changelist tabs", "https://unfoldadmin.com/docs/tabs/changelist/"),
    ("Changeform tabs", "https://unfoldadmin.com/docs/tabs/changeform/"),
    ("Fieldsets tabs", "https://unfoldadmin.com/docs/tabs/fieldsets/"),
    ("Inlines tabs", "https://unfoldadmin.com/docs/tabs/inline/"),
    ("Dynamic tabs", "https://unfoldadmin.com/docs/tabs/dynamic/"),
    ("ArrayWidget", "https://unfoldadmin.com/docs/widgets/array/"),
    ("WysiwygWidget", "https://unfoldadmin.com/docs/widgets/wysiwyg/"),
    ("Inlines introduction", "https://unfoldadmin.com/docs/inlines/introduction/"),
    ("Inline options", "https://unfoldadmin.com/docs/inlines/options/"),
    ("Nonrelated inlines", "https://unfoldadmin.com/docs/inlines/nonrelated/"),
    ("Sortable inlines", "https://unfoldadmin.com/docs/inlines/sortable/"),
    ("Paginated inlines", "https://unfoldadmin.com/docs/inlines/paginated/"),
    ("Nested inlines", "https://unfoldadmin.com/docs/inlines/nested/"),
    ("JsonField", "https://unfoldadmin.com/docs/fields/json/"),
    ("Autocomplete fields", "https://unfoldadmin.com/docs/fields/autocomplete/"),
    ("django-celery-beat", "https://unfoldadmin.com/docs/integrations/django-celery-beat/"),
    ("djangoql", "https://unfoldadmin.com/docs/integrations/djangoql/"),
    ("django-money", "https://unfoldadmin.com/docs/integrations/django-money/"),
    ("django-constance", "https://unfoldadmin.com/docs/integrations/django-constance/"),
    ("django-json-widget", "https://unfoldadmin.com/docs/integrations/django-json-widget/"),
    ("django-import-export", "https://unfoldadmin.com/docs/integrations/django-import-export/"),
    ("django-simple-history", "https://unfoldadmin.com/docs/integrations/django-simple-history/"),
    ("django-guardian", "https://unfoldadmin.com/docs/integrations/django-guardian/"),
    ("django-modeltranslation", "https://unfoldadmin.com/docs/integrations/django-modeltranslation/"),
    ("django-location-field", "https://unfoldadmin.com/docs/integrations/django-location-field/"),
    ("Display decorator", "https://unfoldadmin.com/docs/decorators/display/"),
    ("Action decorator", "https://unfoldadmin.com/docs/decorators/action/"),
    ("Loading styles and scripts", "https://unfoldadmin.com/docs/styles-scripts/loading-files/"),
    ("Customizing Tailwind stylesheet", "https://unfoldadmin.com/docs/styles-scripts/customizing-tailwind/"),
    ("Official demo repository", "https://github.com/unfoldadmin/formula"),
    (
        "Official demo Admin index",
        "https://github.com/unfoldadmin/formula/blob/main/formula/templates/admin/index.html",
    ),
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
    layouts = _names(package_root / "templates/unfold/layouts")
    widget_templates = _names(package_root / "templates/unfold/widgets")
    crispy_layouts = _names(package_root / "templates/unfold_crispy/layout")
    crispy_templates = _names(package_root / "templates/unfold_crispy", recursive=False)
    contrib_templates = _names(package_root / "contrib")
    widgets = _widget_names(package_root / "widgets.py")
    contrib_widgets = _public_defs(package_root / "contrib/forms/widgets.py", suffixes=("Widget",))
    forms = _form_names(package_root / "forms.py")
    contrib_forms = sorted(
        {
            *(
                f"unfold.contrib.filters.forms.{name}"
                for name in _public_defs(
                    package_root / "contrib/filters/forms.py", suffixes=("Form",)
                )
            ),
            *(
                f"unfold.contrib.import_export.forms.{name}"
                for name in _public_defs(
                    package_root / "contrib/import_export/forms.py", suffixes=("Form", "Mixin")
                )
            ),
            *(
                f"unfold.contrib.inlines.forms.{name}"
                for name in _public_defs(
                    package_root / "contrib/inlines/forms.py", suffixes=("Form", "FormSet")
                )
            ),
        }
    )
    admin_primitives = sorted(
        {
            *(
                f"unfold.admin.{name}"
                for name in _public_defs(package_root / "admin.py")
            ),
            *(
                f"unfold.decorators.{name}"
                for name in _public_defs(package_root / "decorators.py")
            ),
            *(
                f"unfold.sections.{name}"
                for name in _public_defs(package_root / "sections.py")
            ),
            *(
                f"unfold.contrib.filters.admin.{path.stem}.{name}"
                for path in (package_root / "contrib/filters/admin").glob("*.py")
                if path.name != "__init__.py"
                for name in _public_defs(path)
            ),
            *(
                f"unfold.contrib.inlines.admin.{name}"
                for name in _public_defs(package_root / "contrib/inlines/admin.py")
            ),
        }
    )

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
                "## Layout Templates",
                "",
                *_bullets(f"`unfold/layouts/{name}`" for name in layouts),
                "",
                "## Widget Templates",
                "",
                *_bullets(f"`unfold/widgets/{name}`" for name in widget_templates),
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
                "## Contrib Widgets",
                "",
                *_bullets(f"`unfold.contrib.forms.widgets.{name}`" for name in contrib_widgets),
                "",
                "## Forms",
                "",
                *_bullets(f"`unfold.forms.{name}`" for name in forms),
                "",
                "## Contrib Forms",
                "",
                *_bullets(f"`{name}`" for name in contrib_forms),
                "",
                "## Admin, Filters, Decorators, Sections, Inlines",
                "",
                *_bullets(f"`{name}`" for name in admin_primitives),
                "",
                "## Contrib Templates",
                "",
                *_bullets(f"`unfold/contrib/{name}`" for name in contrib_templates),
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


def _names(path: Path, *, recursive: bool = True) -> list[str]:
    if not path.exists():
        return []
    finder = path.rglob if recursive else path.glob
    return sorted(item.relative_to(path).as_posix() for item in finder("*.html"))


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


def _public_defs(path: Path, *, suffixes: tuple[str, ...] | None = None) -> list[str]:
    if not path.exists():
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef | ast.FunctionDef):
            continue
        if node.name.startswith("_"):
            continue
        if suffixes and not node.name.endswith(suffixes):
            continue
        names.append(node.name)
    return sorted(names)


def _bullets(items) -> list[str]:
    values = list(items)
    if not values:
        return ["- None found"]
    return [f"- {item}" for item in values]


if __name__ == "__main__":
    raise SystemExit(main())
