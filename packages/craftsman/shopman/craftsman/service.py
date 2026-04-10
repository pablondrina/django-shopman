"""
Craftsman Service — Thin facade over focused service modules.

Usage:
    from shopman.craftsman import craft, CraftError

    wo = craft.plan(recipe, 100)
    craft.adjust(wo, quantity=97, reason='farinha insuficiente')
    craft.close(wo, produced=93)

    # or
    craft.void(wo, reason='cliente cancelou')

4 verbs: plan, adjust, close, void.
3 queries: suggest, needs, expected.
"""

from shopman.craftsman.services.execution import CraftExecution
from shopman.craftsman.services.queries import CraftQueries
from shopman.craftsman.services.scheduling import CraftPlanning


class CraftService(CraftPlanning, CraftExecution, CraftQueries):
    """
    Single interface for all Craftsman operations.

    Follows Stockman's mixin pattern:
        StockService = StockQueries + StockMovements + StockHolds + StockPlanning
        CraftService = CraftPlanning + CraftExecution + CraftQueries

    Models encapsulate invariants. Services orchestrate effects.
    """


# Backward-compatible aliases
Craft = CraftService

# Module-level alias — all methods are @classmethod.
# Allows: from shopman.craftsman.service import craft
craft = CraftService
