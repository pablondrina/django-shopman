"""Validação de documentos fiscais brasileiros (CPF/CNPJ) por dígito verificador.

Acusar CPF errado na digitação (inline) é infinitamente melhor que uma rejeição
assíncrona da SEFAZ depois que o cliente foi embora.
"""

from __future__ import annotations


def _digits(value: str | None) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def is_valid_cpf(value: str | None) -> bool:
    """True se ``value`` é um CPF válido (11 dígitos + verificadores)."""
    cpf = _digits(value)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for check_pos in (9, 10):
        total = sum(int(cpf[i]) * (check_pos + 1 - i) for i in range(check_pos))
        digit = (total * 10) % 11
        if digit == 10:
            digit = 0
        if digit != int(cpf[check_pos]):
            return False
    return True


def is_valid_cnpj(value: str | None) -> bool:
    """True se ``value`` é um CNPJ válido (14 dígitos + verificadores)."""
    cnpj = _digits(value)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    weights_first = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights_second = [6, *weights_first]
    for weights, check_pos in ((weights_first, 12), (weights_second, 13)):
        total = sum(int(cnpj[i]) * weight for i, weight in enumerate(weights))
        digit = total % 11
        digit = 0 if digit < 2 else 11 - digit
        if digit != int(cnpj[check_pos]):
            return False
    return True


def is_valid_tax_id(value: str | None) -> bool:
    """True se ``value`` é CPF (11 dígitos) ou CNPJ (14 dígitos) válido."""
    length = len(_digits(value))
    if length == 11:
        return is_valid_cpf(value)
    if length == 14:
        return is_valid_cnpj(value)
    return False
