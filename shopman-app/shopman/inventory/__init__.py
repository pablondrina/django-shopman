"""
Shopman Stock Contrib — Verificação de disponibilidade e reserva de estoque.

Uso:
    from shopman.inventory.protocols import StockBackend
    from shopman.inventory.handlers import StockHoldHandler
    from shopman.inventory.resolvers import StockIssueResolver

Para usar com Stockman:
    from shopman.inventory.adapters.stockman import StockmanBackend
"""

from .protocols import StockBackend, AvailabilityResult, HoldResult, Alternative

__all__ = [
    "StockBackend",
    "AvailabilityResult",
    "HoldResult",
    "Alternative",
]
