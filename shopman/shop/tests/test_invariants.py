"""
Architectural invariant tests — previne regressões de design.

Estes testes varrem o codebase (grep/AST) para garantir que as decisões
arquiteturais se mantêm ao longo do tempo.

Invariantes verificadas:
1. Nenhuma view/API lê order.data["payment"]["status"] diretamente.
   Detecta tanto padrão inline (.data.get("payment"...).get("status"))
   quanto padrão split (payment = ...; payment.get("status")).
2. Fulfillment tem um único caminho de criação (via service).
3. Handlers delegam para services — sem Fulfillment.objects.create() em handlers.
4. lifecycle dispatchers não contêm classes de lifecycle.
5. ChannelConfig governa os aspectos declarados.
6. Templates não usam inline event handlers (onclick, onchange, etc.).
7. except Exception: pass (sem log) proibido em business logic.
8. Deprecated naming (comanda, parked) não aparece em data keys.
9. Templates não usam document.getElementById (exceções documentadas).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

# ── Root do framework ──
FRAMEWORK_ROOT = Path(__file__).parent.parent

# ── Root do projeto (shopman/) ──
PROJECT_ROOT = FRAMEWORK_ROOT.parent


def _source_files(*sub_paths: str) -> list[Path]:
    """Return .py files under each sub_path relative to FRAMEWORK_ROOT."""
    files = []
    for sp in sub_paths:
        files.extend((FRAMEWORK_ROOT / sp).rglob("*.py"))
    return files


def _template_files(*sub_paths: str) -> list[Path]:
    """Return .html template files under each sub_path relative to PROJECT_ROOT."""
    files = []
    for sp in sub_paths:
        root = PROJECT_ROOT / sp
        if root.exists():
            files.extend(root.rglob("*.html"))
    return files


def _grep(pattern: str, files: list[Path]) -> list[tuple[Path, int, str]]:
    """Return (file, lineno, line) for every line matching pattern."""
    rx = re.compile(pattern)
    hits = []
    for path in files:
        try:
            for lineno, line in enumerate(path.read_text().splitlines(), 1):
                if rx.search(line):
                    hits.append((path, lineno, line.strip()))
        except (OSError, UnicodeDecodeError):
            pass
    return hits


def _scan_split_payment_status(files: list[Path]) -> list[tuple[Path, int, str]]:
    """
    Detect split-statement payment status reads:

        payment = order.data.get("payment", {})
        payment.get("status")          # ← violation

    Walks each file line-by-line, recording any variable assigned from
    `*.data.get("payment"` or `*.data["payment"]`, then flags any later
    access to `.get("status")` or `["status"]` on that variable.
    """
    violations = []
    for path in files:
        try:
            lines = path.read_text().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        if "test_" in path.name:
            continue

        payment_vars: set[str] = set()
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue

            # Detect: varname = ....data.get("payment", ...) or ....data["payment"]
            m = re.match(
                r'(\w+)\s*=\s*.*\.data(?:\.get\(["\']payment["\']|\[["\']payment["\'])',
                stripped,
            )
            if m:
                payment_vars.add(m.group(1))

            # Detect: varname.get("status") or varname["status"]
            for var in list(payment_vars):
                if re.search(
                    rf'\b{re.escape(var)}\s*\.get\(\s*["\']status["\']',
                    stripped,
                ) or re.search(
                    rf'\b{re.escape(var)}\s*\[\s*["\']status["\']',
                    stripped,
                ):
                    violations.append((path, lineno, stripped))

    return violations


# ── Invariant 1: No view/API reads order.data["payment"]["status"] ──


class TestNoDirectPaymentStatusRead:
    """After payment facades landed, views must not poke order.data for payment status."""

    VIEW_FILES = _source_files("web/views", "api")

    PATTERN = r'\.data\s*\.get\(["\']payment["\'].*\.get\(["\']status'

    def test_no_payment_status_from_order_data_in_views(self):
        hits = _grep(self.PATTERN, self.VIEW_FILES)
        # Filter out test files and comments
        real_hits = [
            (p, ln, line)
            for (p, ln, line) in hits
            if not line.strip().startswith("#") and "test_" not in p.name
        ]
        assert not real_hits, (
            "Views/API must use payment_svc.get_payment_status(order) instead of "
            "order.data['payment']['status']. Violations:\n"
            + "\n".join(f"  {p}:{ln}: {line}" for p, ln, line in real_hits)
        )

    def test_no_payment_status_from_order_data_in_handlers(self):
        handler_files = _source_files("handlers")
        hits = _grep(self.PATTERN, handler_files)
        real_hits = [
            (p, ln, line)
            for (p, ln, line) in hits
            if not line.strip().startswith("#") and "test_" not in p.name
        ]
        assert not real_hits, (
            "Handlers must use payment_svc.get_payment_status(order) instead of "
            "order.data['payment']['status']. Violations:\n"
            + "\n".join(f"  {p}:{ln}: {line}" for p, ln, line in real_hits)
        )

    def test_no_split_statement_payment_status_in_views(self):
        """Detect multi-line payment status reads (variable assigned, then .get('status'))."""
        violations = _scan_split_payment_status(self.VIEW_FILES)
        assert not violations, (
            "Views/API must use payment_svc.get_payment_status(order) — "
            "split-statement reads of payment.get('status') are also forbidden. "
            "Violations:\n"
            + "\n".join(f"  {p}:{ln}: {line}" for p, ln, line in violations)
        )

    def test_no_split_statement_payment_status_in_handlers(self):
        """Detect multi-line payment status reads in handlers."""
        handler_files = _source_files("handlers")
        violations = _scan_split_payment_status(handler_files)
        assert not violations, (
            "Handlers must use payment_svc.get_payment_status(order) — "
            "split-statement reads of payment.get('status') are also forbidden. "
            "Violations:\n"
            + "\n".join(f"  {p}:{ln}: {line}" for p, ln, line in violations)
        )


# ── Invariant 2: Fulfillment has single creation path ──


class TestFulfillmentSingleCreationPath:
    """Fulfillment.objects.create() must only appear in services/fulfillment.py."""

    PATTERN = r"Fulfillment\.objects\.create"

    def test_fulfillment_create_only_in_service(self):
        all_py = _source_files(".")
        hits = _grep(self.PATTERN, all_py)
        violations = [
            (p, ln, line)
            for (p, ln, line) in hits
            if "services/fulfillment.py" not in str(p)
            and not line.strip().startswith("#")
            and "test_" not in p.name
        ]
        assert not violations, (
            "Fulfillment.objects.create() must only appear in services/fulfillment.py. "
            "Violations:\n"
            + "\n".join(f"  {p}:{ln}: {line}" for p, ln, line in violations)
        )


# ── Invariant 3: Handlers don't do direct model creation ──


class TestHandlersDelegateToServices:
    """Handlers must not call Model.objects.create() for Order or Fulfillment."""

    HANDLER_FILES = _source_files("handlers")
    FORBIDDEN = [
        r"Order\.objects\.create",
        r"Fulfillment\.objects\.create",
    ]

    @pytest.mark.parametrize("pattern", FORBIDDEN)
    def test_handler_does_not_create_models_directly(self, pattern):
        hits = _grep(pattern, self.HANDLER_FILES)
        real_hits = [
            (p, ln, line)
            for (p, ln, line) in hits
            if not line.strip().startswith("#")
        ]
        assert not real_hits, (
            f"Handlers must not call {pattern} — delegate to services. Violations:\n"
            + "\n".join(f"  {p}:{ln}: {line}" for p, ln, line in real_hits)
        )


# ── Invariant 4: lifecycle dispatchers are function tables ──


class TestNoLifecycleClasses:
    """Lifecycle dispatchers must remain table/function driven."""

    LIFECYCLE_FILE = FRAMEWORK_ROOT / "lifecycle.py"
    PRODUCTION_LIFECYCLE_FILE = FRAMEWORK_ROOT / "production_lifecycle.py"

    @pytest.mark.parametrize("path", [LIFECYCLE_FILE, PRODUCTION_LIFECYCLE_FILE])
    def test_no_classes_in_lifecycle_dispatchers(self, path):
        if not path.exists():
            pytest.skip(f"{path.name} not found")

        tree = ast.parse(path.read_text())
        classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]

        assert not classes, (
            f"{path.name} must not define lifecycle classes; use phase handler maps. "
            f"Found: {classes}"
        )

    def test_lifecycle_uses_phase_handlers_dict(self):
        """lifecycle.py must define _PHASE_HANDLERS mapping."""
        if not self.LIFECYCLE_FILE.exists():
            pytest.skip("lifecycle.py not found")

        source = self.LIFECYCLE_FILE.read_text()
        assert "_PHASE_HANDLERS" in source, (
            "lifecycle.py must define _PHASE_HANDLERS dict for phase dispatch"
        )

    def test_production_lifecycle_uses_phase_handlers_dict(self):
        if not self.PRODUCTION_LIFECYCLE_FILE.exists():
            pytest.skip("production_lifecycle.py not found")

        source = self.PRODUCTION_LIFECYCLE_FILE.read_text()
        assert "_PRODUCTION_PHASE_HANDLERS" in source, (
            "production_lifecycle.py must define _PRODUCTION_PHASE_HANDLERS for dispatch"
        )


def test_channel_model_has_no_kind_field():
    """Channel behavior is resolved by ChannelConfig; no channel kind taxonomy."""
    from shopman.shop.models import Channel

    field_names = {field.name for field in Channel._meta.fields}
    assert "kind" not in field_names


# ── Invariant 5: ChannelConfig governs declared aspects ──


class TestChannelConfigGovernsAspects:
    """ChannelConfig aspects must be read via ChannelConfig.for_channel(), not hard-coded."""

    LIFECYCLE_FILE = FRAMEWORK_ROOT / "lifecycle.py"

    ASPECTS_IN_LIFECYCLE = [
        "config.stock.check_on_commit",
        "config.payment.timing",
        "config.fulfillment.timing",
        "config.confirmation.mode",
    ]

    # auto_sync is consumed in handlers/fulfillment.py, not lifecycle.py
    ASPECTS_IN_HANDLER = [
        ("config.fulfillment.auto_sync", "handlers/fulfillment.py"),
    ]

    @pytest.mark.parametrize("aspect_expr", ASPECTS_IN_LIFECYCLE)
    def test_aspect_is_referenced_in_lifecycle(self, aspect_expr):
        if not self.LIFECYCLE_FILE.exists():
            pytest.skip("lifecycle.py not found")

        source = self.LIFECYCLE_FILE.read_text()
        assert aspect_expr in source, (
            f"lifecycle.py must reference {aspect_expr} to honor ChannelConfig"
        )

    @pytest.mark.parametrize("aspect_expr,file_suffix", [
        ("config.fulfillment.auto_sync", "handlers/fulfillment.py"),
    ])
    def test_aspect_is_referenced_in_handler(self, aspect_expr, file_suffix):
        handler_file = FRAMEWORK_ROOT / file_suffix
        if not handler_file.exists():
            pytest.skip(f"{file_suffix} not found")
        source = handler_file.read_text()
        assert aspect_expr in source, (
            f"{file_suffix} must reference {aspect_expr} to honor ChannelConfig"
        )

    def test_channel_config_loaded_via_for_channel(self):
        """dispatch() must resolve ChannelConfig via for_channel(), not hard-coded values."""
        if not self.LIFECYCLE_FILE.exists():
            pytest.skip("lifecycle.py not found")

        source = self.LIFECYCLE_FILE.read_text()
        assert "ChannelConfig.for_channel" in source, (
            "lifecycle.py must call ChannelConfig.for_channel() to resolve per-channel config"
        )


# ── Invariant 6: No legacy flows.py ──


class TestNoLegacyFlowsModule:
    """flows.py was renamed to lifecycle.py. No re-import of the old name."""

    def test_no_import_from_flows(self):
        all_py = _source_files(".")
        pattern = r"from shopman\.flows import|from shopman import flows\b|import shopman\.flows"
        hits = _grep(pattern, all_py)
        real_hits = [
            (p, ln, line)
            for (p, ln, line) in hits
            if not line.strip().startswith("#") and "test_" not in p.name
        ]
        assert not real_hits, (
            "flows.py was renamed to lifecycle.py. Use 'from shopman.shop.lifecycle import dispatch'. "
            "Violations:\n"
            + "\n".join(f"  {p}:{ln}: {line}" for p, ln, line in real_hits)
        )


# ── Invariant 7: No inline event handlers in templates ──


class TestNoInlineEventHandlers:
    """Templates must use Alpine (@click, @change) or HTMX, never onclick/onchange/onsubmit.

    Exception: offline.html (no Alpine loaded on that page).
    """

    ALL_TEMPLATES = _template_files(
        "backstage/templates",
        "storefront/templates",
        "shop/templates",
    )

    HANDLERS = r'\b(onclick|onchange|onsubmit|onload|onfocus|onblur|onkeydown|onkeyup)\s*='

    # Pages where Alpine is not available
    EXCEPTIONS = {"offline.html"}

    def test_no_inline_handlers(self):
        rx = re.compile(self.HANDLERS)
        violations = []
        for path in self.ALL_TEMPLATES:
            if path.name in self.EXCEPTIONS:
                continue
            try:
                for lineno, line in enumerate(path.read_text().splitlines(), 1):
                    stripped = line.strip()
                    if stripped.startswith("{#") or stripped.startswith("<!--"):
                        continue
                    if rx.search(stripped):
                        violations.append((path, lineno, stripped))
            except (OSError, UnicodeDecodeError):
                pass
        assert not violations, (
            "Templates must use Alpine (@click) or HTMX, never inline event handlers "
            "(onclick, onchange, etc.). Violations:\n"
            + "\n".join(f"  {p}:{ln}: {line}" for p, ln, line in violations)
        )


# ── Invariant 8: No bare except Exception: pass ──


class TestNoBareExceptPass:
    """except Exception: pass (without logging) is prohibited in business logic.

    Every catch-all must at minimum log — silent swallowing hides bugs.
    Covers: services/, handlers/, adapters/, lifecycle.py, omotenashi/.
    """

    BUSINESS_FILES = _source_files(
        "services",
        "handlers",
        "lifecycle.py".replace(".py", ""),  # lifecycle is a file not dir, handle below
    )

    def _get_files(self):
        """Business logic files with catch-all exception observability requirements."""
        files = list(_source_files("services", "handlers", "adapters"))
        files.extend(_source_files("rules", "templatetags"))
        lifecycle = FRAMEWORK_ROOT / "lifecycle.py"
        if lifecycle.exists():
            files.append(lifecycle)
        production_lifecycle = FRAMEWORK_ROOT / "production_lifecycle.py"
        if production_lifecycle.exists():
            files.append(production_lifecycle)
        modifiers = FRAMEWORK_ROOT / "modifiers.py"
        if modifiers.exists():
            files.append(modifiers)
        omotenashi = FRAMEWORK_ROOT / "omotenashi"
        if omotenashi.exists():
            files.extend(omotenashi.rglob("*.py"))
        storefront_root = PROJECT_ROOT / "storefront"
        projections = storefront_root / "projections"
        if projections.exists():
            files.extend(projections.rglob("*.py"))
        pickup_slots = storefront_root / "services" / "pickup_slots.py"
        if pickup_slots.exists():
            files.append(pickup_slots)
        return [f for f in files if "test_" not in f.name]

    def _handler_has_logger(self, node: ast.ExceptHandler) -> bool:
        return any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and isinstance(child.func.value, ast.Name)
            and child.func.value.id == "logger"
            for child in ast.walk(ast.Module(body=node.body, type_ignores=[]))
        )

    def test_no_bare_exception_pass(self):
        """Find except Exception blocks followed only by pass."""
        violations = []
        for path in self._get_files():
            try:
                tree = ast.parse(path.read_text())
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                if not isinstance(node.type, ast.Name) or node.type.id != "Exception":
                    continue
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    violations.append((path, node.lineno, "except Exception"))
        assert not violations, (
            "except Exception: pass is forbidden in business logic. "
            "Every catch-all must log or return an explicit fallback. Violations:\n"
            + "\n".join(f"  {p}:{ln}: {line}" for p, ln, line in violations)
        )

    def test_wp02_scope_catchalls_are_observable(self):
        """Projection/rule catch-all fallbacks must log their intentional degradation."""
        focused_files = list((PROJECT_ROOT / "storefront" / "projections").glob("*.py"))
        focused_files.extend([
            PROJECT_ROOT / "storefront" / "services" / "pickup_slots.py",
            FRAMEWORK_ROOT / "templatetags" / "storefront_tags.py",
            FRAMEWORK_ROOT / "modifiers.py",
        ])
        focused_files.extend((FRAMEWORK_ROOT / "rules").glob("*.py"))

        violations = []
        for path in focused_files:
            if not path.exists():
                continue
            try:
                tree = ast.parse(path.read_text())
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                if not isinstance(node.type, ast.Name) or node.type.id != "Exception":
                    continue
                if not self._handler_has_logger(node):
                    violations.append((path, node.lineno, "except Exception"))
        assert not violations, (
            "WP-02 scoped catch-all fallbacks must log with logger.debug(..., exc_info=True) "
            "or stronger severity for operational loss. Violations:\n"
            + "\n".join(f"  {p}:{ln}: {line}" for p, ln, line in violations)
        )


# ── Invariant 9: No deprecated naming in data keys ──


class TestNoDeprecatedDataKeys:
    """Deprecated Session/Order data key names must not appear in data access patterns.

    Renames: comanda→tab, parked→standby, parked_by→standby_operator.

    Only checks patterns that access .data dict keys or set_data/get operations,
    not Portuguese prose in comments or docstrings.
    """

    ALL_PY = _source_files(".")

    DEPRECATED_KEYS = {
        "comanda": "tab",
        "parked": "standby",
        "parked_by": "standby_operator",
    }

    # Patterns that indicate actual data key usage (not prose):
    #   data["key"], data.get("key"), data__key, set_data("key"), "key": value
    DATA_ACCESS_PATTERNS = [
        r"""data\s*\[\s*['"]{}['"]\s*\]""",       # data["key"] or data['key']
        r"""\.get\(\s*['"]{}['"]""",                # .get("key"
        r"""set_data\(\s*['"]{}['"]""",             # set_data("key"
        r"""data__{}""",                            # data__key (ORM filter)
        r"""['"]{}['"]\s*:""",                      # "key": value (dict literal)
    ]

    def test_no_deprecated_data_keys(self):
        violations = []
        for old_key, new_key in self.DEPRECATED_KEYS.items():
            patterns = [p.format(re.escape(old_key)) for p in self.DATA_ACCESS_PATTERNS]
            combined = re.compile("|".join(patterns))
            for path in self.ALL_PY:
                if "test_" in path.name or "migration" in str(path):
                    continue
                try:
                    for lineno, line in enumerate(path.read_text().splitlines(), 1):
                        stripped = line.strip()
                        if stripped.startswith("#"):
                            continue
                        if combined.search(stripped):
                            violations.append(
                                (path, lineno, f"{stripped}  [use '{new_key}' instead of '{old_key}']")
                            )
                except (OSError, UnicodeDecodeError):
                    pass
        assert not violations, (
            "Deprecated data key names found in data access patterns. "
            "Use the canonical English names. Violations:\n"
            + "\n".join(f"  {p}:{ln}: {line}" for p, ln, line in violations)
        )


# ── Invariant 10: No document.getElementById in templates ──


class TestNoGetElementByIdInTemplates:
    """Templates must use Alpine $refs or $dispatch, not document.getElementById.

    Documented exceptions:
    - hx-vals="js:{...Alpine.$data(document.getElementById(...))...}" — HTMX+Alpine bridge
    - IntersectionObserver callbacks (menu scroll spy) — no Alpine equivalent
    - _design_tokens*.html / _tokens.html — FOUC-prevention scripts run pre-Alpine
    - stock_error_modal.html — HTMX oob-swap sink pattern
    - partials/_bottom_nav.html — cross-fragment badge update (HTMX target)
    """

    ALL_TEMPLATES = _template_files(
        "backstage/templates",
        "storefront/templates",
        "shop/templates",
    )

    # Files with documented legitimate exceptions
    EXCEPTION_FILES = {
        # HTMX hx-vals bridge: Alpine.$data(document.getElementById('pos-root'))
        "pos/index.html",
        # FOUC-prevention (pre-Alpine dark mode init)
        "_tokens.html",
        "_design_tokens_no_alpine.html",
        # IntersectionObserver for scroll spy
        "prototype_menu.html",
        "menu.html",
        # HTMX oob-swap sink pattern
        "stock_error_modal.html",
        "availability_preview.html",
        "_catalog_item_grid.html",
        "product_detail.html",
        # Cross-fragment cart badge update
        "_bottom_nav.html",
    }

    def test_no_get_element_by_id(self):
        pattern = re.compile(r"document\.getElementById")
        violations = []
        for path in self.ALL_TEMPLATES:
            # Check if this file matches any exception
            rel = str(path)
            if any(exc in rel for exc in self.EXCEPTION_FILES):
                continue
            try:
                for lineno, line in enumerate(path.read_text().splitlines(), 1):
                    stripped = line.strip()
                    if stripped.startswith("{#") or stripped.startswith("<!--"):
                        continue
                    if pattern.search(stripped):
                        violations.append((path, lineno, stripped))
            except (OSError, UnicodeDecodeError):
                pass
        assert not violations, (
            "Templates must use Alpine $refs/$dispatch, not document.getElementById. "
            "If this is a legitimate exception, add the filename to EXCEPTION_FILES "
            "with a comment explaining why. Violations:\n"
            + "\n".join(f"  {p}:{ln}: {line}" for p, ln, line in violations)
        )
