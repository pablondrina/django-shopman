"""Architecture guardrails for the 3-surface split.

Enforces the dependency rule:
    storefront ──→ shop ←── backstage
      (never cross)    (shop touches surfaces only via adapters/)
"""

import re
from pathlib import Path

import pytest

# ── Roots ─────────────────────────────────────────────────────────────────────
SHOP_ROOT = Path(__file__).resolve().parent.parent        # shopman/shop/
SHOPMAN_ROOT = SHOP_ROOT.parent                           # shopman/
STOREFRONT_ROOT = SHOPMAN_ROOT / "storefront"
BACKSTAGE_ROOT = SHOPMAN_ROOT / "backstage"

SURFACE_ROOTS = [SHOP_ROOT, STOREFRONT_ROOT, BACKSTAGE_ROOT]

# ── Patterns ──────────────────────────────────────────────────────────────────
KERNEL_PACKAGES = [
    "stockman", "offerman", "craftsman", "orderman",
    "doorman", "payman",
]

DEEP_IMPORT_RE = re.compile(
    r"from\s+shopman\.("
    + "|".join(KERNEL_PACKAGES)
    + r")\.(models|contrib)\.(\w+)"
)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _py_files(root, skip_parts=None):
    skip_parts = skip_parts or set()
    result = []
    for f in sorted(root.rglob("*.py")):
        if "__pycache__" in str(f):
            continue
        if skip_parts & set(f.relative_to(root).parts):
            continue
        result.append(f)
    return result


def _scan(pattern, files, root):
    violations = []
    for f in files:
        try:
            lines = f.read_text().splitlines()
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if pattern.search(stripped):
                violations.append((str(f.relative_to(root)), i, stripped))
    return violations


# ── Tests ─────────────────────────────────────────────────────────────────────
def test_no_cross_surface_imports():
    """storefront must never import backstage, and vice versa (production code only)."""
    sf_violations = _scan(
        re.compile(r"(?:from|import)\s+shopman\.backstage\b"),
        _py_files(STOREFRONT_ROOT, skip_parts={"tests"}),
        STOREFRONT_ROOT,
    )
    bs_violations = _scan(
        re.compile(r"(?:from|import)\s+shopman\.storefront\b"),
        _py_files(BACKSTAGE_ROOT, skip_parts={"tests"}),
        BACKSTAGE_ROOT,
    )
    all_violations = (
        [("storefront/" + f, ln, code) for f, ln, code in sf_violations]
        + [("backstage/" + f, ln, code) for f, ln, code in bs_violations]
    )
    if all_violations:
        report = "\n".join(f"  {f}:{ln}: {code}" for f, ln, code in all_violations)
        pytest.fail(
            f"Found {len(all_violations)} cross-surface import(s):\n{report}\n\n"
            "storefront and backstage must never import each other directly."
        )


def test_shop_imports_surfaces_only_via_adapters():
    """shop/ must not import storefront or backstage except in adapters/ and tests/."""
    files = _py_files(SHOP_ROOT, skip_parts={"adapters", "tests"})
    violations = _scan(
        re.compile(r"(?:from|import)\s+shopman\.(storefront|backstage)\b"),
        files,
        SHOP_ROOT,
    )
    if violations:
        report = "\n".join(f"  shop/{f}:{ln}: {code}" for f, ln, code in violations)
        pytest.fail(
            f"Found {len(violations)} direct surface import(s) in shop/ (outside adapters/):\n{report}\n\n"
            "shop/ must only touch storefront/backstage through adapters/."
        )


def test_no_deep_kernel_imports_all_apps():
    """shop/, storefront/, and backstage/ must not import kernel sub-modules directly."""
    all_violations = []
    for root in SURFACE_ROOTS:
        for f, ln, code in _scan(DEEP_IMPORT_RE, _py_files(root, skip_parts={"tests"}), root):
            all_violations.append((root.name + "/" + f, ln, code))
    if all_violations:
        report = "\n".join(f"  {f}:{ln}: {code}" for f, ln, code in all_violations)
        pytest.fail(
            f"Found {len(all_violations)} deep kernel import(s):\n{report}\n\n"
            "Use package-level imports instead, e.g.:\n"
            "  from shopman.stockman import Hold, HoldStatus\n"
            "  from shopman.offerman import Product"
        )


def test_no_template_shadowing():
    """No two apps may register the same template path (components/ is whitelisted as shared)."""
    template_owners = {}
    conflicts = []

    for root in SURFACE_ROOTS:
        templates_dir = root / "templates"
        if not templates_dir.exists():
            continue
        for tpl in sorted(templates_dir.rglob("*.html")):
            rel = tpl.relative_to(templates_dir)
            if rel.parts[0] == "components":
                continue
            key = str(rel)
            if key in template_owners:
                conflicts.append((key, template_owners[key], root.name))
            else:
                template_owners[key] = root.name

    if conflicts:
        report = "\n".join(
            f"  {path!r}: owned by '{a}' and '{b}'"
            for path, a, b in conflicts
        )
        pytest.fail(
            f"Found {len(conflicts)} shadowed template path(s):\n{report}\n\n"
            "Each template path must belong to exactly one app.\n"
            "(components/ is whitelisted as shared.)"
        )
