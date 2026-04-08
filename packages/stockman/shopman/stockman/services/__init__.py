"""
Stock services — modular organization of stock operations.

Re-exports all public methods so existing code keeps working:
    from shopman.stockman.services import StockQueries, StockMovements, StockHolds, StockPlanning
"""

from shopman.stockman.services.holds import StockHolds
from shopman.stockman.services.movements import StockMovements
from shopman.stockman.services.planning import StockPlanning
from shopman.stockman.services.queries import StockQueries

__all__ = [
    'StockQueries',
    'StockMovements',
    'StockHolds',
    'StockPlanning',
]
