"""
Registry de RefTypes.

RefTypes são registrados aqui para serem acessíveis globalmente.
O registro acontece no AppConfig.ready() da app.
"""

from __future__ import annotations

from shopman.orderman.contrib.refs.types import RefType


class _RefTypeRegistry:
    """Registro central de RefTypes."""

    def __init__(self):
        self._types: dict[str, RefType] = {}

    def register(self, ref_type: RefType) -> None:
        """
        Registra um RefType.

        Raises:
            ValueError: Se já existe RefType com mesmo slug.
        """
        if ref_type.slug in self._types:
            raise ValueError(f"RefType '{ref_type.slug}' already registered")
        self._types[ref_type.slug] = ref_type

    def get(self, slug: str) -> RefType | None:
        """Retorna RefType por slug ou None se não encontrado."""
        return self._types.get(slug)

    def get_all(self) -> list[RefType]:
        """Retorna todos os RefTypes registrados."""
        return list(self._types.values())

    def clear(self) -> None:
        """Limpa o registro. Útil para testes."""
        self._types.clear()


# Instância global
_registry = _RefTypeRegistry()

# API pública
register_ref_type = _registry.register
get_ref_type = _registry.get
get_all_ref_types = _registry.get_all
clear_ref_types = _registry.clear
