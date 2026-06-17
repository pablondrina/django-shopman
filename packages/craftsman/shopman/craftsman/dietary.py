"""Dietary profile of a single insumo, carried in ``RecipeItem.meta``.

Single source of truth for the dietary keys of ``RecipeItem.meta``. The
dataclass drives two things:

1. The Craftsman admin inline form — one field per attribute, no JSON raw.
2. The aggregation service
   (:mod:`shopman.shop.services.dietary_from_recipe`), which unions these
   per-insumo facts into ``Product.metadata['allergens']`` /
   ``['dietary_info']``.

Modelling
---------
- ``allergens`` are the natural pt-BR tokens the insumo *contains*
  (``glúten``, ``leite``, ``ovos``, ``gergelim``, ``castanhas`` …). They are
  stored verbatim; the storefront maps them to customer preferences
  (e.g. ``leite`` → lactose) in
  :mod:`shopman.storefront.presentation.dietary`.
- ``diet`` is the insumo's own diet class. It drives the vegan/vegetarian
  claim: a product is vegan only if **every** insumo is vegan; vegetarian
  only if **no** insumo is of animal (slaughter) origin.

An item is considered "declared" only when its ``meta`` carries the ``diet``
key. The aggregation refuses to claim anything (allergen labelling is a
safety concern) unless *all* insumos are declared — see the service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Diet classification of a single insumo.
DIET_VEGAN = "vegan"            # plant-based — OK for vegans and vegetarians
DIET_VEGETARIAN = "vegetarian"  # animal-derived, no slaughter (milk, eggs, honey)
DIET_ANIMAL = "animal"          # requires slaughter (meat, fish, gelatin)
DIET_CLASSES: tuple[str, ...] = (DIET_VEGAN, DIET_VEGETARIAN, DIET_ANIMAL)

DIET_LABELS_PT: dict[str, str] = {
    DIET_VEGAN: "Vegano (origem vegetal)",
    DIET_VEGETARIAN: "Vegetariano (leite/ovos)",
    DIET_ANIMAL: "Origem animal (carne/peixe)",
}


@dataclass(frozen=True)
class IngredientDietary:
    """Dietary facts of one insumo, serialized into ``RecipeItem.meta``."""

    allergens: tuple[str, ...] = ()
    diet: str = DIET_VEGAN

    @classmethod
    def from_meta(cls, meta: dict[str, Any] | None) -> IngredientDietary | None:
        """Read the dietary profile from ``RecipeItem.meta``.

        Returns ``None`` when the item does not declare a dietary profile
        (no ``diet`` key) — the caller treats that as "unknown", not "safe".
        """
        if not isinstance(meta, dict) or "diet" not in meta:
            return None
        raw_allergens = meta.get("allergens") or []
        if isinstance(raw_allergens, (list, tuple)):
            allergens = tuple(str(a).strip() for a in raw_allergens if str(a).strip())
        else:
            allergens = ()
        diet = str(meta.get("diet") or DIET_VEGAN).strip().lower()
        if diet not in DIET_CLASSES:
            diet = DIET_VEGAN
        return cls(allergens=allergens, diet=diet)

    def to_meta(self) -> dict[str, Any]:
        """Serialize to the ``RecipeItem.meta`` keys (``allergens`` + ``diet``)."""
        return {"allergens": list(self.allergens), "diet": self.diet}
