"""Validação de CPF/CNPJ por dígito verificador."""

import pytest

from shopman.utils.documents import is_valid_cnpj, is_valid_cpf, is_valid_tax_id


@pytest.mark.parametrize("cpf", ["529.982.247-25", "52998224725", "111.444.777-35"])
def test_valid_cpfs(cpf):
    assert is_valid_cpf(cpf) is True


@pytest.mark.parametrize(
    "cpf",
    ["52998224724", "11111111111", "00000000000", "1234567890", "123456789012", "", None],
)
def test_invalid_cpfs(cpf):
    assert is_valid_cpf(cpf) is False


@pytest.mark.parametrize("cnpj", ["11.222.333/0001-81", "11222333000181"])
def test_valid_cnpjs(cnpj):
    assert is_valid_cnpj(cnpj) is True


@pytest.mark.parametrize("cnpj", ["11222333000180", "11111111111111", "123", "", None])
def test_invalid_cnpjs(cnpj):
    assert is_valid_cnpj(cnpj) is False


def test_tax_id_dispatches_by_length():
    assert is_valid_tax_id("529.982.247-25") is True
    assert is_valid_tax_id("11.222.333/0001-81") is True
    assert is_valid_tax_id("12345") is False
