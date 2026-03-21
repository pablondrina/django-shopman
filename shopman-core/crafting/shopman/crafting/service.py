"""
Craftsman Service — Thin facade over focused service modules.

Usage:
    from shopman.crafting import craft, CraftError

    wo = craft.plan(recipe, 100)
    craft.adjust(wo, quantity=97, reason='farinha insuficiente')
    craft.close(wo, produced=93)

    # or
    craft.void(wo, reason='cliente cancelou')

4 verbs: plan, adjust, close, void.
3 queries: suggest, needs, expected.
"""

from shopman.crafting.services.execution import CraftExecution
from shopman.crafting.services.queries import CraftQueries
from shopman.crafting.services.scheduling import CraftPlanning


class Craft(CraftPlanning, CraftExecution, CraftQueries):
    """
    Single interface for all Craftsman operations.

    Follows Stockman's mixin pattern:
        Stock = StockQueries + StockMovements + StockHolds + StockPlanning
        Craft = CraftPlanning + CraftExecution + CraftQueries

    Models encapsulate invariants. Services orchestrate effects.
    """


# Module-level alias — all methods are @classmethod.
# Allows: from shopman.crafting.service import craft
craft = Craft
