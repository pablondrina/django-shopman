"""Invariant: NO silent broad `except Exception` in shop/storefront.

Backstage already enforces zero silent broad catches (test_exception_hygiene);
shop and storefront are now at zero too (the faxina B2 backlog was driven down
to 0 on 2026-05-30). Every broad catch must log (logger./logging.) or re-raise
within ~4 lines. Baselines are kept at 0 — never raise them; fix the catch.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

EXCEPT_PATTERN = re.compile(r"^\s*except\s+Exception\b")
LOG_OR_RAISE = re.compile(r"\b(logger\.|log\.|logging\.|raise\b)")

# Zero silent broad catches across all surfaces. Keep at 0.
BASELINES = {"shop": 0, "storefront": 0}

_ROOT = Path(__file__).resolve().parents[2]  # shopman/


def _count_silent(layer: str) -> int:
    root = _ROOT / layer
    silent = 0
    for path in root.rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines):
            if not EXCEPT_PATTERN.match(line):
                continue
            window = "\n".join(lines[idx + 1 : idx + 5])
            if not LOG_OR_RAISE.search(window):
                silent += 1
    return silent


@pytest.mark.parametrize("layer", sorted(BASELINES))
def test_silent_broad_except_does_not_grow(layer: str) -> None:
    current = _count_silent(layer)
    ceiling = BASELINES[layer]
    assert current <= ceiling, (
        f"{layer}: {current} silent broad excepts > baseline {ceiling}. "
        f"Add logger.*/raise within ~4 lines of the `except Exception`. "
        f"If you FIXED some, lower BASELINES['{layer}'] to {current}."
    )
