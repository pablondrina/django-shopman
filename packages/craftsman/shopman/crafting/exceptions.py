"""
Crafting Exceptions.

All crafting errors are wrapped in CraftError for consistent handling.
"""

from shopman.utils.exceptions import BaseError


class CraftError(BaseError):
    """
    Base exception for all Crafting errors.

    Usage:
        raise CraftError('INVALID_STATUS', current='pending', expected='open')
        raise CraftError('INVALID_QUANTITY', quantity=-1)

    Attributes:
        code: Error code (INVALID_QUANTITY, TERMINAL_STATUS, etc.)
        message: Human-readable description
        data: Additional context as keyword arguments
    """

    _default_messages = {
        "INVALID_QUANTITY": "Quantity must be greater than zero",
        "TERMINAL_STATUS": "Cannot modify a work order in terminal status",
        "VOID_FROM_DONE": "Cannot void a completed work order",
        "STALE_REVISION": "Work order was modified by another process",
        "BOM_CYCLE": "BOM expansion exceeded maximum depth",
        "RECIPE_NOT_FOUND": "Recipe not found",
        "WORK_ORDER_NOT_FOUND": "Work order not found",
        "COMMITTED_HOLDS": "Quantity below committed orders for this date",
        "INSUFFICIENT_MATERIALS": "Insufficient shared ingredients for rescheduled quantity",
        "DOWNSTREAM_DEFICIT": "Reducing this work order creates ingredient shortage for downstream production",
    }


class StaleRevision(CraftError):
    """Raised when expected_rev does not match the current rev."""

    def __init__(self, order, expected_rev):
        super().__init__(
            "STALE_REVISION",
            expected_rev=expected_rev,
            current_rev=order.rev,
            work_order=order.code,
        )
