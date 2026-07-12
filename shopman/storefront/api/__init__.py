"""Shopman API — REST endpoints (DRF)."""

from __future__ import annotations

from typing import Any


def clean_text(value: Any) -> str:
    """Coerce a JSON body field to a stripped string, safely.

    A text field arriving as int/list/dict/bool (``{"code": 42}``) must never
    reach ``.strip()`` on a non-string and blow up as a 500 with a leaked
    traceback. Non-strings are treated as absent (empty), so the caller's
    required-field guard turns type-confusion into a clean 400.
    """
    return value.strip() if isinstance(value, str) else ""
