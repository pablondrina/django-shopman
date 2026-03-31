"""
CraftingCostBackend — production cost from recipes.

Implements CostBackend protocol by reading Recipe + RecipeItem data.
Each RecipeItem can store unit_cost_q in its meta field.

Cost per unit = sum(item.quantity * item.meta["unit_cost_q"]) / recipe.batch_size
"""

from __future__ import annotations

import logging
from decimal import Decimal

from shopman.offering.protocols.cost import CostBackend

logger = logging.getLogger(__name__)


class CraftingCostBackend:
    """
    CostBackend that calculates production cost from Crafting recipes.

    For each RecipeItem, reads ``meta["unit_cost_q"]`` (cost per unit of
    input in centavos). Items without unit_cost_q are skipped.

    Returns cost per output unit (total / batch_size), rounded to int.
    """

    def get_cost(self, sku: str) -> int | None:
        from shopman.crafting.models import Recipe

        recipe = (
            Recipe.objects.filter(output_ref=sku, is_active=True)
            .prefetch_related("items")
            .first()
        )
        if recipe is None:
            return None

        total = Decimal("0")
        has_cost_data = False

        for item in recipe.items.all():
            unit_cost_q = item.meta.get("unit_cost_q") if item.meta else None
            if unit_cost_q is None:
                continue
            has_cost_data = True
            total += item.quantity * Decimal(str(unit_cost_q))

        if not has_cost_data:
            return None

        cost_per_unit = total / recipe.batch_size
        return int(cost_per_unit.quantize(Decimal("1")))


# Verify protocol compliance at import time.
if not isinstance(CraftingCostBackend(), CostBackend):
    raise TypeError("CraftingCostBackend does not implement CostBackend protocol")
