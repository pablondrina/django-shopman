"""Ratchet invariant: silent broad `except Exception` must not grow in shop/storefront.

Backstage already enforces zero silent broad catches (test_exception_hygiene).
shop and storefront carry a known backlog (faxina B2,
docs/reports/upper-layers-smell-audit-2026-05-29.md). This test freezes that
backlog as a ceiling: any NEW silent broad catch (no logger./raise within ~4
lines) fails the build. Drive the baselines DOWN to 0 as the backlog is fixed —
never up.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

EXCEPT_PATTERN = re.compile(r"^\s*except\s+Exception\b")
LOG_OR_RAISE = re.compile(r"\b(logger\.|log\.|logging\.|raise\b)")

# Current backlog ceilings (measured 2026-05-29). LOWER as you fix; never raise.
BASELINES = {"shop": 36, "storefront": 19}

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
