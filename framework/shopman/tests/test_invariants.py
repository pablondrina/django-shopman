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
4. lifecycle.py não contém classes Flow.
5. ChannelConfig governa os aspectos declarados.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

# ── Root do framework ──
FRAMEWORK_ROOT = Path(__file__).parent.parent


def _source_files(*sub_paths: str) -> list[Path]:
    """Return .py files under each sub_path relative to FRAMEWORK_ROOT."""
    files = []
    for sp in sub_paths:
        files.extend((FRAMEWORK_ROOT / sp).rglob("*.py"))
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


# ── Invariant 4: lifecycle.py has no Flow classes ──


class TestNoFlowClassesInLifecycle:
    """lifecycle.py must not define class *Flow* — behavior is config-driven."""

    LIFECYCLE_FILE = FRAMEWORK_ROOT / "lifecycle.py"

    def test_no_flow_classes_in_lifecycle(self):
        if not self.LIFECYCLE_FILE.exists():
            pytest.skip("lifecycle.py not found")

        source = self.LIFECYCLE_FILE.read_text()
        tree = ast.parse(source)

        flow_classes = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and "Flow" in node.name
        ]

        assert not flow_classes, (
            "lifecycle.py must not define Flow classes — use _PHASE_HANDLERS dict instead. "
            f"Found: {flow_classes}"
        )

    def test_lifecycle_uses_phase_handlers_dict(self):
        """lifecycle.py must define _PHASE_HANDLERS mapping."""
        if not self.LIFECYCLE_FILE.exists():
            pytest.skip("lifecycle.py not found")

        source = self.LIFECYCLE_FILE.read_text()
        assert "_PHASE_HANDLERS" in source, (
            "lifecycle.py must define _PHASE_HANDLERS dict for phase dispatch"
        )


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
            "flows.py was renamed to lifecycle.py. Use 'from shopman.lifecycle import dispatch'. "
            "Violations:\n"
            + "\n".join(f"  {p}:{ln}: {line}" for p, ln, line in real_hits)
        )
