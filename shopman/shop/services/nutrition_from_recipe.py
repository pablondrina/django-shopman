"""Derive Product.ingredients_text + nutrition_facts from a Craftsman Recipe.

Design (see ``docs/decisions/adr-008-pdp-nutrition.md``):

- Product is the surface. Projection reads ``product.ingredients_text``
  and ``product.nutrition_facts`` directly, never imports Craftsman.
- When a Recipe is active and its ``output_ref`` matches a Product SKU,
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
  present, otherwise ``input_ref``).
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from shopman.offerman.models import Product
from shopman.offerman.nutrition import NUTRIENT_FIELDS, NutritionFacts

logger = logging.getLogger(__name__)


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
        from shopman.craftsman.models import Recipe
    except ImportError:
        logger.debug("nutrition_from_recipe: craftsman not installed.")
        return False

    recipe = (
        Recipe.objects.filter(output_ref=product.sku, is_active=True)
        .order_by("-updated_at")
        .first()
    )
    if recipe is None:
        return False

    items = list(recipe.items.all().order_by("-quantity", "sort_order"))
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


def _build_ingredients_text(items) -> str:
    """Join RecipeItem labels in decreasing-weight order (already sorted).

    Falls back to ``input_ref`` when the item has no ``meta["label"]``.
    """
    names: list[str] = []
    for item in items:
        meta = item.meta if isinstance(item.meta, dict) else {}
        label = (meta.get("label") or "").strip()
        if not label:
            label = item.input_ref
        if label:
            names.append(label)
    if not names:
        return ""
    return ", ".join(names) + "."


def _sum_nutrition(items, batch_size: Decimal, product: Product) -> NutritionFacts | None:
    """Sum per-100g insumo profiles into a per-serving dict.

    Math:
    - Each item contributes ``(item.quantity / batch_size) * 1000 g`` of
      insumo per unit produced (assuming batch unit = kg; we treat the
      RecipeItem quantity numerically and normalize by serving mass).
    - The resulting per-unit mass-in-grams is multiplied by
      ``nutrition_per_100g / 100`` to get absolute grams of each nutrient
      in one produced unit.
    - We then scale to ``serving_size_g`` (defaults to
      ``product.unit_weight_g`` when available; otherwise we emit the
      absolute per-unit numbers and set serving_size to unit_weight or 0).
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
        has_any_nutrition = True
        # grams of this insumo per unit produced
        grams_per_unit = (float(item.quantity) / float(batch_size)) * 1000.0
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

    serving_size_g = product.unit_weight_g or 0

    return NutritionFacts(
        serving_size_g=int(serving_size_g),
        servings_per_container=1,
        energy_kcal=_round(totals["energy_kcal"], 0),
        carbohydrates_g=_round(totals["carbohydrates_g"], 1),
        sugars_g=_round(totals["sugars_g"], 1),
        proteins_g=_round(totals["proteins_g"], 1),
        total_fat_g=_round(totals["total_fat_g"], 1),
        saturated_fat_g=_round(totals["saturated_fat_g"], 1),
        trans_fat_g=_round(totals["trans_fat_g"], 2),
        fiber_g=_round(totals["fiber_g"], 1),
        sodium_mg=_round(totals["sodium_mg"], 0),
        auto_filled=True,
    )


def _round(value: float, digits: int) -> float | None:
    """Round or return ``None`` when the running sum stayed at 0."""
    if value == 0:
        return None
    return round(value, digits)
