"""Conversão de valores EFI (decimal BRL → centavos) nunca pode passar por float.

Regressão do audit pré-go-live: ``int(float("4.35") * 100) == 434`` — o
capture-check reconciliava 434q contra um intent de 435q (mismatch permanente)
e refunds registravam 1 centavo a menos (drift no ledger).
"""

import pytest

from shopman.shop.adapters.payment_efi import _brl_to_q


@pytest.mark.parametrize(
    ("valor", "expected_q"),
    [
        ("4.35", 435),  # float trunca para 434
        ("115.70", 11570),
        ("0.29", 29),  # float trunca para 28
        ("10", 1000),
        ("0.01", 1),
        (4.35, 435),
    ],
)
def test_brl_to_q_never_truncates(valor, expected_q):
    assert _brl_to_q(valor) == expected_q
