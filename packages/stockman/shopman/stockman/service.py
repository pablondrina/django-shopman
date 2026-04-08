"""
Stock Service — The single public interface for all stock operations.

Usage:
    from shopman.stockman import stock, StockError

    stock.plan(50, croissant, friday)
    hold_id = stock.hold(5, croissant, friday)
    stock.available(croissant, friday)  # 45

Implementation is split into modules under stocking/services/:
    queries.py    — available, demand, committed, get_quant, list_quants
    movements.py  — receive, issue, adjust
    holds.py      — hold, confirm, release, fulfill, release_expired
    planning.py   — plan, replan, realize
"""

from shopman.stockman.services.holds import StockHolds
from shopman.stockman.services.movements import StockMovements
from shopman.stockman.services.planning import StockPlanning
from shopman.stockman.services.queries import StockQueries


class StockService(StockQueries, StockMovements, StockHolds, StockPlanning):
    """
    Single interface for all stock operations.

    Parameter convention: (quantity, product, target_date, ...)
    Follows natural language: "Plan 50 croissants for Friday"

    IMPORTANT: All state-changing methods use atomic transactions
    with appropriate locking. See each method's docstring.
    """


# Backward-compatible alias
Stock = StockService
