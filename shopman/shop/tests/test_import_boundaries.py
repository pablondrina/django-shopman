"""AST-backed import boundary guardrails.

These tests enforce the architectural direction that is easy to regress:

* kernel packages do not import host/orchestrator/surface apps;
* surfaces do not import each other;
* shop imports surfaces only through adapters;
* framework code does not import protected kernel internals.

The checks intentionally parse Python imports instead of using line regexes so
both ``import x.y`` and ``from x.y import z`` are covered.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FRAMEWORK_ROOT = REPO_ROOT / "shopman"
PACKAGES_ROOT = REPO_ROOT / "packages"

SHOP_ROOT = FRAMEWORK_ROOT / "shop"
STOREFRONT_ROOT = FRAMEWORK_ROOT / "storefront"
BACKSTAGE_ROOT = FRAMEWORK_ROOT / "backstage"

SURFACE_ROOTS = (SHOP_ROOT, STOREFRONT_ROOT, BACKSTAGE_ROOT)

HOST_PREFIXES = (
    "config",
    "instances",
    "shopman.shop",
    "shopman.storefront",
    "shopman.backstage",
)

PROTECTED_KERNEL_PACKAGES = (
    "refs",
    "utils",
    "stockman",
    "offerman",
    "craftsman",
    "orderman",
    "doorman",
    "payman",
)


def _py_files(root: Path, *, skip_parts: set[str] | None = None) -> Iterable[Path]:
    skip_parts = skip_parts or set()
    for path in sorted(root.rglob("*.py")):
        rel_parts = set(path.relative_to(root).parts)
        if "__pycache__" in rel_parts:
            continue
        if skip_parts & rel_parts:
            continue
        yield path


def _imports(path: Path) -> Iterable[tuple[int, str]]:
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except UnicodeDecodeError:
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.lineno, node.module


def _matches_prefix(module: str, prefixes: Iterable[str]) -> bool:
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)


def _format_violations(violations: list[tuple[Path, int, str]]) -> str:
    return "\n".join(
        f"  {path.relative_to(REPO_ROOT)}:{line}: {module}"
        for path, line, module in violations
    )


def test_kernel_packages_do_not_import_host_layers():
    """Kernel packages must remain standalone and never import host layers."""
    violations = []

    for package_root in sorted(p for p in PACKAGES_ROOT.iterdir() if p.is_dir()):
        for path in _py_files(package_root, skip_parts={"tests"}):
            for line, module in _imports(path):
                if _matches_prefix(module, HOST_PREFIXES):
                    violations.append((path, line, module))

    if violations:
        pytest.fail(
            "Kernel packages imported host/orchestrator/surface modules:\n"
            f"{_format_violations(violations)}\n\n"
            "Move host-specific behavior behind an optional integration resolved "
            "through Django's app registry, settings, or a protocol adapter."
        )


def test_surfaces_do_not_import_each_other():
    """storefront and backstage are sibling surfaces and must not cross-import."""
    checks = (
        (STOREFRONT_ROOT, ("shopman.backstage",)),
        (BACKSTAGE_ROOT, ("shopman.storefront",)),
    )
    violations = []
    for root, forbidden in checks:
        for path in _py_files(root, skip_parts={"tests"}):
            for line, module in _imports(path):
                if _matches_prefix(module, forbidden):
                    violations.append((path, line, module))

    if violations:
        pytest.fail(
            "Cross-surface imports found:\n"
            f"{_format_violations(violations)}\n\n"
            "Use shop-level orchestration or a shared kernel contract instead."
        )


def test_shop_imports_surfaces_only_through_adapters():
    """The orchestrator core may touch surfaces only in shop/adapters/."""
    violations = []
    for path in _py_files(SHOP_ROOT, skip_parts={"adapters", "tests"}):
        for line, module in _imports(path):
            if _matches_prefix(module, ("shopman.storefront", "shopman.backstage")):
                violations.append((path, line, module))

    if violations:
        pytest.fail(
            "Direct surface imports found in shop outside adapters:\n"
            f"{_format_violations(violations)}\n\n"
            "Keep surface integration inside shop/adapters/."
        )


def test_framework_does_not_import_protected_kernel_internals():
    """Framework code should consume kernel package APIs, not internals."""
    violations = []
    for root in SURFACE_ROOTS:
        for path in _py_files(root, skip_parts={"tests"}):
            for line, module in _imports(path):
                parts = module.split(".")
                if (
                    len(parts) >= 4
                    and parts[0] == "shopman"
                    and parts[1] in PROTECTED_KERNEL_PACKAGES
                    and parts[2] in {"models", "contrib"}
                ):
                    violations.append((path, line, module))

    if violations:
        pytest.fail(
            "Framework imported protected kernel internals:\n"
            f"{_format_violations(violations)}\n\n"
            "Use package-level exports, public services, settings, or protocol "
            "adapters instead of models.<submodule> or contrib.<submodule> imports."
        )


def test_surfaces_do_not_import_orderman_write_primitives():
    """Surfaces must create/modify/commit sessions through shop services."""
    forbidden = (
        "shopman.orderman.ids",
        "shopman.orderman.services.commit",
        "shopman.orderman.services.modify",
    )
    violations = []
    for root in (STOREFRONT_ROOT, BACKSTAGE_ROOT):
        for path in _py_files(root, skip_parts={"tests", "projections"}):
            for line, module in _imports(path):
                if _matches_prefix(module, forbidden):
                    violations.append((path, line, module))

    if violations:
        pytest.fail(
            "Surfaces imported Orderman write primitives directly:\n"
            f"{_format_violations(violations)}\n\n"
            "Use shopman.shop.services.sessions or shopman.shop.services.checkout "
            "so session writes have one canonical orchestration path."
        )


def test_backstage_views_do_not_drive_order_lifecycle_directly():
    """Backstage HTTP views must delegate order lifecycle commands to shop services."""
    violations = []
    forbidden_imports = (
        "shopman.shop.lifecycle",
        "shopman.craftsman.services",
        "shopman.stockman",
    )

    for path in _py_files(BACKSTAGE_ROOT / "views"):
        for line, module in _imports(path):
            if _matches_prefix(module, forbidden_imports):
                violations.append((path, line, module))

        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "transition_status":
                    violations.append((path, node.lineno, "transition_status"))

    if violations:
        pytest.fail(
            "Backstage views drove order lifecycle directly:\n"
            f"{_format_violations(violations)}\n\n"
            "Move operator/KDS/production commands into shopman.shop.services and keep "
            "views focused on HTTP, permissions, and rendering."
        )
