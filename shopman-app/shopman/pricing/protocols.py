"""
Shopman Pricing Protocols — Interfaces para backends de precificação.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PricingBackend(Protocol):
    """
    Protocol para backends de precificação.

    Implementações devem fornecer método para obter preço de um SKU.
    """

    def get_price(
        self,
        sku: str,
        channel: Any,
    ) -> int | None:
        """
        Retorna preço em q (centavos) para um SKU.

        Args:
            sku: Código do produto
            channel: Canal de venda

        Returns:
            Preço em q (centavos) ou None se não encontrado
        """
        ...
