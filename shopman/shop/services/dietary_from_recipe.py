"""Derive Product.metadata['allergens'] + ['dietary_info'] from a Recipe.

Mirror of :mod:`shopman.shop.services.nutrition_from_recipe`, for the
dietary axis that ADR-008 deliberately postponed (nutrients are an
arithmetic sum; allergens are a *union* and require per-insumo flags).

Design
------
- Product is the surface. The storefront reads
  ``product.metadata['allergens']`` / ``['dietary_info']`` directly
  (see :mod:`shopman.storefront.presentation.dietary`); it never imports
  Craftsman.
- When a Recipe is active and its ``output_sku`` matches a Product SKU,
  this service unions the dietary profile of every leaf insumo
  (:class:`shopman.craftsman.dietary.IngredientDietary`) and writes the
  result back onto the Product. Called from the same Recipe ``post_save``
  signal as the nutrition derivation (``shop.apps`` wires it).
- Idempotent and **refuses to overwrite a manual override**. The sentinel
  is ``metadata['dietary_auto_filled']``: explicit ``False`` blocks; absent
  or ``True`` is fillable (so the recipe — the source of truth — wins).
- Bundles (``is_bundle=True``) are skipped, like nutrition.
- **Safety:** allergen labelling is materialized only when *every* leaf
  insumo declares a dietary profile. A single undeclared insumo means we
  cannot guarantee what is absent, so we leave whatever is there untouched
  rather than risk an under-reported allergen or a false "sem X" claim.

Derived ``dietary_info`` uses exactly the tokens the storefront preference
filter understands: ``100% vegetal`` / ``vegetariano`` (strongest positive
diet claim) plus the free-from claims ``sem glúten`` / ``sem lactose``.
"""

from __future__ import annotations

import logging
from typing import Any

from shopman.craftsman.dietary import (
    DIET_ANIMAL,
    DIET_VEGAN,
    IngredientDietary,
)
from shopman.offerman.models import Product

logger = logging.getLogger(__name__)

# Allergen tokens that defeat a free-from claim. Matched case-insensitively
# against the unioned allergen list. Kept aligned with the storefront
# preference triggers in ``storefront.presentation.dietary``.
GLUTEN_TOKENS = frozenset({"glúten", "gluten", "trigo", "cevada", "centeio", "malte"})
LACTOSE_TOKENS = frozenset({"lactose", "leite", "laticínios", "laticinios", "manteiga"})


def aggregate_dietary_from_recipe(product: Product) -> bool:
    """Materialize allergens + dietary_info from the active Recipe.

    Returns ``True`` when the product was updated, ``False`` otherwise
    (no recipe, manual override, bundle, incomplete insumo data, no change).
    Never raises on business conditions — logs and returns ``False``.
    """
    if product.is_bundle:
        logger.debug("dietary_from_recipe: %s is a bundle; skipping.", product.sku)
        return False

    if not _is_auto_filled(product.metadata):
        logger.info(
            "dietary_from_recipe: %s has manual override "
            "(dietary_auto_filled=False); skipping.", product.sku,
        )
        return False

    try:
        from shopman.craftsman.services.recipes import get_active_recipe_for_output_sku
    except ImportError:
        logger.debug("dietary_from_recipe: craftsman not installed.")
        return False

    recipe = get_active_recipe_for_output_sku(product.sku)
    if recipe is None:
        return False

    from shopman.shop.services.recipe_bom import expand_recipe_items

    items = expand_recipe_items(recipe)
    if not items:
        return False

    profiles: list[IngredientDietary] = []
    for item in items:
        meta = item.meta if isinstance(item.meta, dict) else {}
        profile = IngredientDietary.from_meta(meta)
        if profile is None:
            logger.info(
                "dietary_from_recipe: %s has insumo without dietary profile (%s); "
                "skipping (incomplete data is unsafe for allergen labelling).",
                product.sku, item.input_sku,
            )
            return False
        profiles.append(profile)

    allergens = _union_allergens(profiles)
    dietary_info = _derive_dietary_info(profiles, allergens)

    current = product.metadata or {}
    new_metadata = dict(current)
    new_metadata["allergens"] = allergens
    new_metadata["dietary_info"] = dietary_info
    new_metadata["dietary_auto_filled"] = True

    if new_metadata == current:
        return False

    product.metadata = new_metadata
    product.save(update_fields=["metadata"])
    logger.info(
        "dietary_from_recipe: %s updated (allergens=%s, dietary_info=%s).",
        product.sku, allergens, dietary_info,
    )
    return True


# ──────────────────────────────────────────────────────────────────────
# Internals
# ──────────────────────────────────────────────────────────────────────


def _is_auto_filled(metadata: dict[str, Any] | None) -> bool:
    """A missing sentinel counts as auto-fillable; explicit False blocks."""
    if not metadata:
        return True
    if "dietary_auto_filled" in metadata:
        return bool(metadata.get("dietary_auto_filled"))
    return True


def _union_allergens(profiles: list[IngredientDietary]) -> list[str]:
    """Union of insumo allergens, in first-appearance order (heaviest first)."""
    seen: list[str] = []
    for profile in profiles:
        for allergen in profile.allergens:
            if allergen not in seen:
                seen.append(allergen)
    return seen


def _derive_dietary_info(
    profiles: list[IngredientDietary], allergens: list[str]
) -> list[str]:
    """Strongest positive diet claim + free-from claims, storefront tokens."""
    diets = {profile.diet for profile in profiles}
    info: list[str] = []

    if diets <= {DIET_VEGAN}:
        info.append("100% vegetal")
    elif DIET_ANIMAL not in diets:
        info.append("vegetariano")

    lowered = {a.lower() for a in allergens}
    if not (lowered & GLUTEN_TOKENS):
        info.append("sem glúten")
    if not (lowered & LACTOSE_TOKENS):
        info.append("sem lactose")

    return info
