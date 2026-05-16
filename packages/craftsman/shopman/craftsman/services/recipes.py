"""Recipe resolution helpers.

Craftsman links products and BOMs through SKU string refs. This module keeps
that contract deterministic: a SKU can have zero or one active production
recipe unless a future route model makes alternates explicit.
"""

from __future__ import annotations

from shopman.craftsman.exceptions import CraftError


def get_active_recipe_for_output_sku(output_sku: str, *, prefetch_items: bool = False):
    """Return the single active recipe for ``output_sku`` or ``None``.

    Ambiguity is a configuration error. The database constraint prevents new
    duplicates; this guard makes old or externally loaded data fail loudly.
    """
    sku = str(output_sku or "").strip()
    if not sku:
        return None

    from shopman.craftsman.models import Recipe

    qs = Recipe.objects.filter(output_sku=sku, is_active=True).order_by("pk")
    if prefetch_items:
        qs = qs.prefetch_related("items")
    matches = list(qs[:2])
    if not matches:
        return None
    if len(matches) > 1:
        raise CraftError("AMBIGUOUS_RECIPE", output_sku=sku)
    return matches[0]


def has_active_recipe_for_output_sku(output_sku: str) -> bool:
    """Return whether ``output_sku`` has an active production recipe."""
    sku = str(output_sku or "").strip()
    if not sku:
        return False

    from shopman.craftsman.models import Recipe

    return Recipe.objects.filter(output_sku=sku, is_active=True).exists()
