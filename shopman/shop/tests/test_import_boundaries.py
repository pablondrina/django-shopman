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
import re
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

# Data read-side (Projection) and the surface Presentation layers — targets of
# the ADR-014 §4.2 semantic cut (rules R-A/R-B/R-C/R-D).
PROJECTIONS_ROOT = SHOP_ROOT / "projections"
PRESENTATION_ROOTS = (
    STOREFRONT_ROOT / "presentation",
    BACKSTAGE_ROOT / "presentation",
)

HOST_PREFIXES = (
    "config",
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
        for path in _py_files(root, skip_parts={"tests", "presentation"}):
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
    """Backstage HTTP views must delegate order lifecycle mutations to shop services."""
    violations = []
    forbidden_imports = (
        "shopman.orderman",
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
            "Move operator/KDS/production mutations into shopman.shop.services and keep "
            "views focused on HTTP, permissions, and rendering."
        )


def test_storefront_api_delegates_kernel_mutations():
    """Storefront public APIs must keep kernel reads/writes behind services."""
    forbidden = (
        "shopman.guestman",
        "shopman.doorman",
        "shopman.orderman",
        "shopman.offerman",
        "shopman.stockman",
        "shopman.payman",
        "shopman.craftsman",
    )
    violations = []

    for path in _py_files(STOREFRONT_ROOT / "api"):
        for line, module in _imports(path):
            if _matches_prefix(module, forbidden):
                violations.append((path, line, module))

    if violations:
        pytest.fail(
            "Storefront APIs imported kernel modules directly:\n"
            f"{_format_violations(violations)}\n\n"
            "Route API reads and mutations through shopman.shop.services.* or "
            "surface-local projection services when no orchestration is needed."
        )


def test_storefront_surface_reads_delegate_kernel_domains():
    """Storefront services/projections/intents must read kernels through shop services."""
    forbidden = (
        "shopman.guestman",
        "shopman.doorman",
        "shopman.orderman",
        "shopman.offerman",
        "shopman.stockman",
        "shopman.payman",
        "shopman.craftsman",
    )
    roots = (
        STOREFRONT_ROOT / "services",
        STOREFRONT_ROOT / "presentation",
        STOREFRONT_ROOT / "intents",
    )
    violations = []

    for root in roots:
        for path in _py_files(root):
            for line, module in _imports(path):
                if _matches_prefix(module, forbidden):
                    violations.append((path, line, module))

    if violations:
        pytest.fail(
            "Storefront service/projection/intent modules imported kernel modules directly:\n"
            f"{_format_violations(violations)}\n\n"
            "Route domain reads and mutations through shopman.shop.services.* so "
            "surface modules stay HTTP/template/read-model adapters."
        )


def test_storefront_keeps_customer_auth_mutations_in_shop_services():
    """Customer auth/access/device mutations belong to the orchestrator."""
    forbidden_service_modules = (
        STOREFRONT_ROOT / "services" / "auth.py",
        STOREFRONT_ROOT / "services" / "access.py",
        STOREFRONT_ROOT / "services" / "devices.py",
    )
    violations = [
        (path, 1, "shopman.storefront.services")
        for path in forbidden_service_modules
        if path.exists()
    ]

    if violations:
        pytest.fail(
            "Storefront reintroduced customer auth/access/device mutation services:\n"
            f"{_format_violations(violations)}\n\n"
            "Use shopman.shop.services.auth/access/devices so Doorman and Guestman "
            "coordination has one canonical orchestration path."
        )


def test_storefront_keeps_checkout_mutations_in_shop_services():
    """Checkout commit and post-commit coordination belongs to the orchestrator."""
    forbidden_service_modules = (
        STOREFRONT_ROOT / "services" / "checkout.py",
        STOREFRONT_ROOT / "services" / "checkout_defaults.py",
        STOREFRONT_ROOT / "services" / "ifood_simulation.py",
    )
    violations = [
        (path, 1, "shopman.storefront.services")
        for path in forbidden_service_modules
        if path.exists()
    ]

    if violations:
        pytest.fail(
            "Storefront reintroduced checkout mutation services:\n"
            f"{_format_violations(violations)}\n\n"
            "Use shopman.shop.services.checkout/checkout_defaults/ifood_simulation "
            "so checkout commit, customer persistence, and simulated marketplace "
            "ingest have one canonical orchestration path."
        )


def test_storefront_checkout_intent_delegates_domain_resolution():
    """Checkout intent parsing must not resolve kernel domains directly."""
    path = STOREFRONT_ROOT / "intents" / "checkout.py"
    forbidden = (
        "shopman.guestman",
        "shopman.offerman",
        "shopman.stockman",
        "shopman.orderman",
    )
    violations = []

    for line, module in _imports(path):
        if _matches_prefix(module, forbidden):
            violations.append((path, line, module))

    if violations:
        pytest.fail(
            "Storefront checkout intent imported kernel modules directly:\n"
            f"{_format_violations(violations)}\n\n"
            "Keep request/form interpretation in storefront and route customer, "
            "catalog, stock, and loyalty resolution through "
            "shopman.shop.projections.checkout_context."
        )


def test_storefront_cart_intent_delegates_product_resolution():
    """Cart intent parsing must not resolve catalog/stock domains directly."""
    path = STOREFRONT_ROOT / "intents" / "cart.py"
    forbidden = (
        "shopman.offerman",
        "shopman.stockman",
    )
    violations = []

    for line, module in _imports(path):
        if _matches_prefix(module, forbidden):
            violations.append((path, line, module))

    if violations:
        pytest.fail(
            "Storefront cart intent imported catalog/stock modules directly:\n"
            f"{_format_violations(violations)}\n\n"
            "Keep cart intent parsing in storefront and route product price/D-1 "
            "resolution through shopman.shop.projections.cart_context."
        )


def test_storefront_cart_delegates_write_mutations():
    """Storefront cart adapter must call shop cart mutations."""
    path = STOREFRONT_ROOT / "cart.py"
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))

    forbidden_names = {
        "modify_session",
        "create_session",
        "abandon_session",
    }
    forbidden_availability = {"reserve", "reconcile"}
    violations: list[tuple[Path, int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "availability"
                and node.func.attr in forbidden_availability
            ):
                violations.append((path, node.lineno, f"availability.{node.func.attr}"))
            if node.func.attr in forbidden_names:
                violations.append((path, node.lineno, node.func.attr))

    if violations:
        pytest.fail(
            "Storefront cart performed write mutations directly:\n"
            f"{_format_violations(violations)}\n\n"
            "Keep request/session adaptation in storefront.cart and route cart mutations "
            "through shopman.shop.services.cart."
        )


# O boundary "POS views delegam writes aos services" saiu com a view POS-HTMX
# (SURFACE-CONVERGENCE-PLAN WP1). O POS agora é o Nuxt sobre api/v1/backstage/pos/*,
# cuja camada de write são os próprios services (contrato headless adr-012/014).


# ──────────────────────────────────────────────────────────────────────
# ADR-014 §4.2 — the data/presentation cut (R-A · R-B · R-C · R-D)
#
# These codify the semantic boundary: data Projections (shop/projections/) carry
# only meaning; each surface's Presentation places appearance. See
# docs/decisions/adr-014-surface-data-presentation-cut.md and
# docs/redesign/04-architecture.md §4.2.
# ──────────────────────────────────────────────────────────────────────


def _string_constants(tree: ast.AST) -> Iterable[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.lineno, node.value


def test_presentation_reads_only_the_read_side():
    """R-A · ``<surface>/presentation/`` may read ``shop.projections`` but never
    ``shop.services`` (write-side). Mutation stays in views/intents."""
    violations: list[tuple[Path, int, str]] = []
    for root in PRESENTATION_ROOTS:
        if not root.exists():
            continue
        for path in _py_files(root, skip_parts={"tests"}):
            for line, module in _imports(path):
                if _matches_prefix(module, ("shopman.shop.services",)):
                    violations.append((path, line, module))

    if violations:
        pytest.fail(
            "Presentation imported the write-side (shop.services):\n"
            f"{_format_violations(violations)}\n\n"
            "Presentation consumes only shop.projections (Projection + Action). "
            "Route mutations through views/intents calling shop.services."
        )


# Tailwind colour/tone design-token classes — appearance, owned by each
# surface's Presentation (rule R-B keeps them out of the data read-side).
_TONE_CLASS_RE = re.compile(
    r"\b(?:bg|text|border)-(?:info|warning|success|danger|muted|surface-alt)\b"
    r"|text-on-surface"
)
# Money/locale formatting and template/HTML helpers are appearance, not data.
_BANNED_PROJECTION_IMPORTS = (
    "shopman.utils.monetary",  # format_money — presentation
    "django.template",
    "django.utils.html",
)


def test_data_projections_carry_no_appearance():
    """R-B · ``shop/projections/`` does not import money/locale/template/HTML
    helpers, nor embed Tailwind colour-token classes (appearance lives in the
    surface Presentation).

    NOTE: the broader "no PT-BR UX copy literal" half of R-B is *not* enforced
    yet — Action labels and confirmation copy still live in
    catalog_context/cart/checkout/payment_status/storefront_context/
    order_tracking. Draining those into OmotenashiCopy is the remaining S7 work
    (see project_wp7_pos_status / docs/redesign/04-architecture.md §S7).
    """
    violations: list[tuple[Path, int, str]] = []
    for path in _py_files(PROJECTIONS_ROOT, skip_parts={"tests"}):
        for line, module in _imports(path):
            if _matches_prefix(module, _BANNED_PROJECTION_IMPORTS):
                violations.append((path, line, f"import {module}"))
        tree = ast.parse(path.read_text(), filename=str(path))
        for line, value in _string_constants(tree):
            if _TONE_CLASS_RE.search(value):
                violations.append((path, line, f"tailwind colour class: {value!r}"))

    if violations:
        pytest.fail(
            "Data Projections carried appearance (rule R-B):\n"
            f"{_format_violations(violations)}\n\n"
            "Keep shop/projections semantic: emit a Tone enum (mapped to classes "
            "by each surface) and format money/copy in the Presentation."
        )


def test_data_projections_are_frozen_and_channel_agnostic():
    """R-C · ``shop/projections/`` dataclasses are ``frozen=True`` and the
    read-side ignores the HTTP/render channel (no ``django.http``)."""
    violations: list[tuple[Path, int, str]] = []
    for path in _py_files(PROJECTIONS_ROOT, skip_parts={"tests"}):
        for line, module in _imports(path):
            if _matches_prefix(module, ("django.http",)):
                violations.append((path, line, f"import {module}"))
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for deco in node.decorator_list:
                target = deco.func if isinstance(deco, ast.Call) else deco
                if not (isinstance(target, ast.Name) and target.id == "dataclass"):
                    continue
                frozen = isinstance(deco, ast.Call) and any(
                    kw.arg == "frozen"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                    for kw in deco.keywords
                )
                if not frozen:
                    violations.append((path, node.lineno, f"non-frozen dataclass {node.name}"))

    if violations:
        pytest.fail(
            "Data Projections were mutable or channel-aware (rule R-C):\n"
            f"{_format_violations(violations)}\n\n"
            "Mark every shop/projections dataclass frozen=True and keep "
            "django.http out of the read-side."
        )


def test_no_second_card_shape_returns():
    """R-D · the retired second card shape and its parallel template stay gone."""
    forbidden = (
        FRAMEWORK_ROOT / "storefront" / "presentation" / "product_cards.py",
        FRAMEWORK_ROOT / "storefront" / "projections" / "product_cards.py",
        STOREFRONT_ROOT / "templates" / "storefront" / "components" / "availability_preview.html",
    )
    existing = [p for p in forbidden if p.exists()]
    # Belt-and-suspenders: also catch a relocated product_cards.py anywhere.
    existing += [
        p for p in FRAMEWORK_ROOT.rglob("product_cards.py") if "__pycache__" not in p.parts
    ]
    if existing:
        listed = "\n".join(f"  {p.relative_to(REPO_ROOT)}" for p in sorted(set(existing)))
        pytest.fail(
            "A retired second card shape/template reappeared (rule R-D):\n"
            f"{listed}\n\n"
            "There is one card shape; do not reintroduce product_cards.py or "
            "availability_preview.html."
        )
