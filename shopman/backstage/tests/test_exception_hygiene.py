"""Invariant: every `except Exception` in backstage logs or re-raises.

Silent broad catches mask bugs in production. Each catch site must either
log via `logger.*` (within ~3 lines) or re-raise.
"""

from __future__ import annotations

import re
from pathlib import Path

BACKSTAGE_ROOT = Path(__file__).resolve().parents[1]
EXCEPT_PATTERN = re.compile(r"^\s*except\s+Exception\b")
LOG_OR_RAISE = re.compile(r"\b(logger\.|raise\b)")


def _iter_source_files():
    for path in BACKSTAGE_ROOT.rglob("*.py"):
        if "tests" in path.parts or "__pycache__" in path.parts or "migrations" in path.parts:
            continue
        yield path


def test_no_silent_broad_except():
    violations: list[str] = []
    for path in _iter_source_files():
        lines = path.read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines):
            if not EXCEPT_PATTERN.match(line):
                continue
            window = "\n".join(lines[idx + 1 : idx + 5])
            if not LOG_OR_RAISE.search(window):
                rel = path.relative_to(BACKSTAGE_ROOT.parent.parent)
                violations.append(f"{rel}:{idx + 1} — broad except without log/raise")
    assert not violations, "Silent broad except sites:\n" + "\n".join(violations)
