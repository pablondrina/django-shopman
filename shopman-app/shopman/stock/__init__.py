"""
Shopman Stock Contrib — Verificação de disponibilidade e reserva de estoque.

Uso:
    from shopman.stock.protocols import StockBackend
    from shopman.stock.handlers import StockHoldHandler
    from shopman.stock.resolvers import StockIssueResolver

Para usar com Stockman:
    from shopman.stock.adapters.stockman import StockmanBackend
"""

from .protocols import StockBackend, AvailabilityResult, HoldResult, Alternative

__all__ = [
    "StockBackend",
    "AvailabilityResult",
    "HoldResult",
    "Alternative",
]
