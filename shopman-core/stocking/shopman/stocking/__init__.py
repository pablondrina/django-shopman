"""
Django Stockman — Motor Unificado de Estoque.

O parceiro de dança perfeito para o Django Salesman.

Uso:
    from shopman.stocking import stock, StockError
    
    stock.plan(50, croissant, sexta)
    stock.hold(5, croissant, sexta)
    stock.available(croissant, sexta)  # 45
"""


def __getattr__(name):
    """Lazy import to avoid circular imports during app loading."""
    if name == 'stock':
        from shopman.stocking.service import Stock
        return Stock
    elif name == 'StockError':
        from shopman.stocking.exceptions import StockError
        return StockError
    elif name == 'Position':
        from shopman.stocking.models.position import Position
        return Position
    elif name == 'Quant':
        from shopman.stocking.models.quant import Quant
        return Quant
    elif name == 'Move':
        from shopman.stocking.models.move import Move
        return Move
    elif name == 'Hold':
        from shopman.stocking.models.hold import Hold
        return Hold
    elif name == 'PositionKind':
        from shopman.stocking.models.enums import PositionKind
        return PositionKind
    elif name == 'HoldStatus':
        from shopman.stocking.models.enums import HoldStatus
        return HoldStatus
    elif name == 'StockAlert':
        from shopman.stocking.models.alert import StockAlert
        return StockAlert
    elif name == 'Batch':
        from shopman.stocking.models.batch import Batch
        return Batch
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    'stock',
    'StockError',
    'Position',
    'Quant',
    'Move',
    'Hold',
    'PositionKind',
    'HoldStatus',
    'StockAlert',
    'Batch',
]

__version__ = '0.3.0'
