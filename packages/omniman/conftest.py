import pytest

from shopman.omniman import registry


@pytest.fixture(autouse=True)
def _clean_registry():
    """Limpa registry entre testes para evitar vazamento de estado."""
    registry.clear()
    yield
    registry.clear()
