"""Shared BOM expansion for Recipe-derived materialization.

A Recipe's technical sheet can reference sub-products that have their own
active Recipe (multilevel BOM). Both the nutrition derivation
(:mod:`shopman.shop.services.nutrition_from_recipe`) and the dietary
derivation (:mod:`shopman.shop.services.dietary_from_recipe`) need the same
thing: the flat list of *leaf* insumos behind a finished product.

``expand_recipe_items`` walks the tree, recursing into sub-recipes with
cycle protection (``MAX_BOM_DEPTH``) and skipping optional alternatives.
``item.quantity`` is scaled by the accumulated coefficient so callers that
do per-unit math (nutrition) get correct quantities; callers that only need
ingredient identity (dietary) ignore it.
"""

from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

MAX_BOM_DEPTH = 5


def expand_recipe_items(
    recipe, *, coefficient: Decimal = Decimal("1"), depth: int = 0
) -> list:
    """Return the leaf RecipeItems behind ``recipe`` (sub-recipes expanded)."""
    if depth > MAX_BOM_DEPTH:
        logger.warning("recipe_bom: recursive recipe depth exceeded for %s", recipe.ref)
        return []

    try:
        from shopman.craftsman.services.recipes import get_active_recipe_for_output_sku
    except ImportError:
        return []

    expanded: list = []
    for item in recipe.items.filter(is_optional=False).order_by("-quantity", "sort_order"):
        sub_recipe = get_active_recipe_for_output_sku(item.input_sku)
        if sub_recipe:
            sub_coefficient = coefficient * (item.quantity / sub_recipe.batch_size)
            expanded.extend(
                expand_recipe_items(sub_recipe, coefficient=sub_coefficient, depth=depth + 1)
            )
            continue
        item.quantity = item.quantity * coefficient
        expanded.append(item)
    return expanded
