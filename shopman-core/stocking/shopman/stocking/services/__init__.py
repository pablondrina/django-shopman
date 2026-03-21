"""
Stock services — modular organization of stock operations.

Re-exports all public methods so existing code keeps working:
    from shopman.stocking.services import StockQueries, StockMovements, StockHolds, StockPlanning
"""

from shopman.stocking.services.holds import StockHolds
from shopman.stocking.services.movements import StockMovements
from shopman.stocking.services.planning import StockPlanning
from shopman.stocking.services.queries import StockQueries

__all__ = [
    'StockQueries',
    'StockMovements',
    'StockHolds',
    'StockPlanning',
]
