"""
Django Stockman — Motor Unificado de Estoque.

O parceiro de dança perfeito para o Django Salesman.

Uso:
    from shopman.stockman import stock, StockError
    
    stock.plan(50, croissant, sexta)
    stock.hold(5, croissant, sexta)
    stock.available(croissant, sexta)  # 45
"""


def __getattr__(name):
    """Lazy import to avoid circular imports during app loading."""
    if name == 'stock':
        from shopman.stockman.service import StockService
        return StockService
    elif name == 'StockService':
        from shopman.stockman.service import StockService
        return StockService
    elif name == 'Stock':
        from shopman.stockman.service import StockService
        return StockService
    elif name == 'StockError':
        from shopman.stockman.exceptions import StockError
        return StockError
    elif name == 'Position':
        from shopman.stockman.models.position import Position
        return Position
    elif name == 'Quant':
        from shopman.stockman.models.quant import Quant
        return Quant
    elif name == 'Move':
        from shopman.stockman.models.move import Move
        return Move
    elif name == 'Hold':
        from shopman.stockman.models.hold import Hold
        return Hold
    elif name == 'PositionKind':
        from shopman.stockman.models.enums import PositionKind
        return PositionKind
    elif name == 'HoldStatus':
        from shopman.stockman.models.enums import HoldStatus
        return HoldStatus
    elif name == 'StockAlert':
        from shopman.stockman.models.alert import StockAlert
        return StockAlert
    elif name == 'Batch':
        from shopman.stockman.models.batch import Batch
        return Batch
    elif name == 'StockHolds':
        from shopman.stockman.services.holds import StockHolds
        return StockHolds
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    'stock',
    'StockService',
    'Stock',
    'StockError',
    'Position',
    'Quant',
    'Move',
    'Hold',
    'PositionKind',
    'HoldStatus',
    'StockAlert',
    'Batch',
    'StockHolds',
]

__version__ = '0.3.0'
