"""W7 — parsing do "troco para" (Reais → centavos) no checkout."""

from __future__ import annotations

import pytest

from shopman.storefront.intents.checkout import _parse_change_for


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("50", 5000),
        ("50,00", 5000),
        ("50.00", 5000),
        ("50,50", 5050),
        ("R$ 50,00", 5000),
        (" 100 ", 10000),
        ("0", 0),
        ("", 0),
        ("abc", 0),
        ("-10", 0),  # negativo não faz sentido p/ troco
        (None, 0),
    ],
)
def test_parse_change_for(raw, expected):
    assert _parse_change_for(raw) == expected
