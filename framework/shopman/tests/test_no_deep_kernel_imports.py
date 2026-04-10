"""Lint: framework must not import kernel internals directly.

The framework should use the public API surfaces exported in each package's
``__init__.py`` (e.g. ``from shopman.stockman import Hold, HoldStatus``).

Importing from ``shopman.<package>.models.<submodule>`` or
``shopman.<package>.contrib.<submodule>`` bypasses the public API contract and
couples the framework to kernel internals.

Allowed deep imports:
- ``shopman.<package>.services.*`` — services are the public API layer
- ``shopman.<package>.conf`` — package settings
- ``shopman.<package>.models`` (top-level, not sub-modules)
- ``shopman.<package>.exceptions``
- Test files inside packages/ (kernel self-tests)
"""

import re
from pathlib import Path

import pytest

FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent  # framework/shopman/

# Packages whose internals must not be imported directly (WP-C scope).
# guestman.contrib is tracked separately as C4 (WP-F).
KERNEL_PACKAGES = [
    "stockman", "offerman", "craftsman", "omniman",
    "doorman", "payman",
]

# Pattern: from shopman.<pkg>.models.<sub> or from shopman.<pkg>.contrib.<sub>
DEEP_IMPORT_RE = re.compile(
    r"from\s+shopman\.("
    + "|".join(KERNEL_PACKAGES)
    + r")\.(models|contrib)\.(\w+)"
)


# Test files are allowed slightly deeper access (e.g. doorman test utilities).
TEST_DIR_PARTS = {"tests"}


def _scan_framework_files():
    """Yield (file, line_number, line) for deep kernel imports."""
    violations = []
    for py_file in sorted(FRAMEWORK_ROOT.rglob("*.py")):
        # Skip __pycache__
        if "__pycache__" in str(py_file):
            continue
        # Test files get a pass on deep imports
        if TEST_DIR_PARTS & set(py_file.relative_to(FRAMEWORK_ROOT).parts):
            continue

        rel = py_file.relative_to(FRAMEWORK_ROOT)
        try:
            lines = py_file.read_text().splitlines()
        except UnicodeDecodeError:
            continue

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if DEEP_IMPORT_RE.search(stripped):
                violations.append((str(rel), i, stripped))

    return violations


def test_no_deep_kernel_imports():
    """Framework must not import kernel sub-modules directly."""
    violations = _scan_framework_files()
    if violations:
        report = "\n".join(
            f"  {f}:{line_no}: {code}"
            for f, line_no, code in violations
        )
        pytest.fail(
            f"Found {len(violations)} deep kernel import(s) in framework:\n{report}\n\n"
            "Use package-level imports instead, e.g.:\n"
            "  from shopman.stockman import Hold, HoldStatus\n"
            "  from shopman.doorman import TrustedDevice"
        )
