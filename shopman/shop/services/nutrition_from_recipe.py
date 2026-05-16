"""Derive Product.ingredients_text + nutrition_facts from a Craftsman Recipe.

Design (see ``docs/decisions/adr-008-pdp-nutrition.md``):

- Product is the surface. Projection reads ``product.ingredients_text``
  and ``product.nutrition_facts`` directly, never imports Craftsman.
- When a Recipe is active and its ``output_sku`` matches a Product SKU,
  this service materializes both fields on the product. Called from:
  - a post_save signal on Recipe (shop.apps wires it);
  - a management command for bulk backfill.
- The service is idempotent and **refuses to overwrite a manual override**.
  The sentinel is ``nutrition_facts["auto_filled"]``: if absent/False,
  the current value is treated as manual and left alone.
- Bundles (``product.is_bundle=True``) are explicitly skipped — see ADR
  for rationale (summing component nutrition is too fragile for food
  labelling).

Ingredient profile lookup:
- Each ``RecipeItem.meta`` may carry::

      {
          "label": "Farinha de trigo",            # pt-BR, for ingredients_text
          "nutrition": {                           # per 100 g of the insumo
              "energy_kcal": 364,
              "carbohydrates_g": 76,
              ...
          }
      }

  Items without ``nutrition`` are ignored for nutritional totals but
  still contribute to ``ingredients_text`` (using ``label`` when
  present, otherwise ``input_sku``).
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from math import ceil
from typing import Any

from shopman.offerman.models import Product
from shopman.offerman.nutrition import NUTRIENT_FIELDS, NutritionFacts

logger = logging.getLogger(__name__)

MASS_UNIT_TO_GRAMS = {
    "kg": Decimal("1000"),
    "g": Decimal("1"),
    "mg": Decimal("0.001"),
}
VOLUME_UNIT_TO_ML = {
    "L": Decimal("1000"),
    "ml": Decimal("1"),
}


def fill_nutrition_from_recipe(product: Product) -> bool:
    """Materialize ingredients_text + nutrition_facts from the active Recipe.

    Returns ``True`` when the product was updated, ``False`` otherwise
    (no recipe, manual override present, bundle, etc.). Never raises on
    business conditions — logs and returns False.
    """
    if product.is_bundle:
        logger.debug(
            "nutrition_from_recipe: %s is a bundle; skipping.", product.sku,
        )
        return False

    if not _is_auto_filled(product.nutrition_facts):
        logger.info(
            "nutrition_from_recipe: %s has manual override (auto_filled=False); "
            "skipping.", product.sku,
        )
        return False

    try:
        from shopman.craftsman.services.recipes import get_active_recipe_for_output_sku
    except ImportError:
        logger.debug("nutrition_from_recipe: craftsman not installed.")
        return False

    recipe = get_active_recipe_for_output_sku(product.sku)
    if recipe is None:
        return False

    items = _expand_recipe_items(recipe)
    if not items:
        return False

    ingredients_text = _build_ingredients_text(items)
    nutrition = _sum_nutrition(items, recipe.batch_size, product)

    update_fields: list[str] = []
    if ingredients_text and ingredients_text != product.ingredients_text:
        product.ingredients_text = ingredients_text
        update_fields.append("ingredients_text")
    if nutrition is not None:
        new_dict = asdict(nutrition)
        if new_dict != (product.nutrition_facts or {}):
            product.nutrition_facts = new_dict
            update_fields.append("nutrition_facts")

    if not update_fields:
        return False

    product.save(update_fields=update_fields)
    logger.info(
        "nutrition_from_recipe: %s updated (%s).",
        product.sku, ", ".join(update_fields),
    )
    return True


# ──────────────────────────────────────────────────────────────────────
# Internals
# ──────────────────────────────────────────────────────────────────────


def _is_auto_filled(nutrition_facts: dict[str, Any] | None) -> bool:
    """A blank dict counts as auto-fillable; explicit False blocks."""
    if not nutrition_facts:
        return True
    return bool(nutrition_facts.get("auto_filled", False))


def _expand_recipe_items(recipe, *, coefficient: Decimal = Decimal("1"), depth: int = 0) -> list:
    if depth > 5:
        logger.warning("nutrition_from_recipe: recursive recipe depth exceeded for %s", recipe.ref)
        return []

    try:
        from shopman.craftsman.services.recipes import get_active_recipe_for_output_sku
    except ImportError:
        return []

    expanded = []
    for item in recipe.items.filter(is_optional=False).order_by("-quantity", "sort_order"):
        sub_recipe = get_active_recipe_for_output_sku(item.input_sku)
        if sub_recipe:
            sub_coefficient = coefficient * (item.quantity / sub_recipe.batch_size)
            expanded.extend(_expand_recipe_items(sub_recipe, coefficient=sub_coefficient, depth=depth + 1))
            continue
        item.quantity = item.quantity * coefficient
        expanded.append(item)
    return expanded


def _build_ingredients_text(items) -> str:
    """Join RecipeItem labels in decreasing-weight order (already sorted).

    Falls back to ``input_sku`` when the item has no ``meta["label"]``.
    """
    names: list[str] = []
    for item in items:
        meta = item.meta if isinstance(item.meta, dict) else {}
        label = (meta.get("label") or "").strip()
        if not label:
            label = item.input_sku
        if label:
            names.append(label)
    if not names:
        return ""
    return ", ".join(names) + "."


def _sum_nutrition(items, batch_size: Decimal, product: Product) -> NutritionFacts | None:
    """Sum per-100g insumo profiles into a per-serving dict.

    Math:
    - Each item is converted to grams before the per-unit calculation.
      Volume and unit counts require ``meta["density_g_per_ml"]`` or
      ``meta["unit_weight_g"]`` respectively; otherwise they are ignored
      for nutritional totals because per-100g math would be unsafe.
    - The resulting per-unit mass-in-grams is multiplied by
      ``nutrition_per_100g / 100`` to get absolute grams of each nutrient
      in one produced unit.
    - We then scale to a consumer-friendly serving:
      ``min(100g, product.unit_weight_g)``. A 400g bread is shown per 100g;
      a 50g bread is shown per unit.
    """
    if not items or batch_size <= 0:
        return None

    totals: dict[str, float] = dict.fromkeys(NUTRIENT_FIELDS, 0.0)
    has_any_nutrition = False

    for item in items:
        meta = item.meta if isinstance(item.meta, dict) else {}
        profile = meta.get("nutrition") or {}
        if not profile:
            continue
        item_grams = _item_quantity_grams(item)
        if item_grams is None:
            logger.warning(
                "nutrition_from_recipe: skipping %s with unit=%s; grams conversion unavailable.",
                item.input_sku,
                item.unit,
            )
            continue
        has_any_nutrition = True
        grams_per_unit = float(item_grams / batch_size)
        for field in NUTRIENT_FIELDS:
            per_100g = profile.get(field)
            if per_100g is None:
                continue
            try:
                totals[field] += float(per_100g) * (grams_per_unit / 100.0)
            except (TypeError, ValueError):
                continue

    if not has_any_nutrition:
        return None

    unit_weight_g = int(product.unit_weight_g or 0)
    serving_size_g = min(100, unit_weight_g) if unit_weight_g > 0 else 100
    serving_scale = (serving_size_g / unit_weight_g) if unit_weight_g > 0 else 1.0
    servings_per_container = max(1, ceil(unit_weight_g / serving_size_g)) if unit_weight_g > 0 else 1

    return NutritionFacts(
        serving_size_g=int(serving_size_g),
        servings_per_container=servings_per_container,
        energy_kcal=_round(totals["energy_kcal"] * serving_scale, 0),
        carbohydrates_g=_round(totals["carbohydrates_g"] * serving_scale, 1),
        sugars_g=_round(totals["sugars_g"] * serving_scale, 1),
        proteins_g=_round(totals["proteins_g"] * serving_scale, 1),
        total_fat_g=_round(totals["total_fat_g"] * serving_scale, 1),
        saturated_fat_g=_round(totals["saturated_fat_g"] * serving_scale, 1),
        trans_fat_g=_round(totals["trans_fat_g"] * serving_scale, 2),
        fiber_g=_round(totals["fiber_g"] * serving_scale, 1),
        sodium_mg=_round(totals["sodium_mg"] * serving_scale, 0),
        auto_filled=True,
    )


def _item_quantity_grams(item) -> Decimal | None:
    unit = str(getattr(item, "unit", "") or "").strip()
    quantity = Decimal(str(item.quantity))
    if unit in MASS_UNIT_TO_GRAMS:
        return quantity * MASS_UNIT_TO_GRAMS[unit]

    meta = item.meta if isinstance(item.meta, dict) else {}
    if unit in VOLUME_UNIT_TO_ML:
        density = _positive_decimal(meta.get("density_g_per_ml"))
        if density is None:
            return None
        return quantity * VOLUME_UNIT_TO_ML[unit] * density

    if unit == "un":
        unit_weight = _positive_decimal(meta.get("unit_weight_g"))
        if unit_weight is None:
            return None
        return quantity * unit_weight

    return None


def _positive_decimal(value) -> Decimal | None:
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return decimal if decimal > 0 else None


def _round(value: float, digits: int) -> float | None:
    """Round or return ``None`` when the running sum stayed at 0."""
    if value == 0:
        return None
    return round(value, digits)
