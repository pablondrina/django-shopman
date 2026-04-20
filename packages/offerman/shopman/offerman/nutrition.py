"""Nutritional facts for a sellable product.

Single source of truth for the schema of ``Product.nutrition_facts``
(JSONField). The dataclass drives three things:

1. Python-side autocomplete / typing when services read/write the dict.
2. Admin form rendering — one field per nutrient, no JSON raw in UI.
3. Validation of ANVISA invariants via ``Product.clean()``.

Reference: ANVISA RDC 360/2003 (rotulagem nutricional obrigatória no Brasil).
The Brazilian Daily Reference Values (DRV) used for %VD default to the
2000 kcal standard defined in Resolução RDC 360/2003.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any

# Daily reference values (DRV) for a 2000 kcal diet — ANVISA RDC 360/2003.
# Used by ``percent_daily_value`` to compute %VD for each nutrient.
DRV_2000_KCAL: dict[str, float] = {
    "energy_kcal": 2000.0,
    "carbohydrates_g": 300.0,
    "proteins_g": 75.0,
    "total_fat_g": 55.0,
    "saturated_fat_g": 22.0,
    # trans_fat_g: ANVISA does not set a DRV; recommendation is "as low as possible".
    "fiber_g": 25.0,
    "sodium_mg": 2400.0,
    # sugars_g: no DRV defined by ANVISA.
}


@dataclass(frozen=True)
class NutritionFacts:
    """Per-serving nutritional profile for a product.

    All numeric fields are optional (``None``) so partial labels are
    representable. ``serving_size_g`` is the only non-optional numeric
    field when any other nutrient is present — enforced by
    ``Product.clean()``.

    ``auto_filled=True`` marks a value derived automatically from a
    Recipe (see ``nutrition_from_recipe.fill_nutrition_from_recipe``).
    The derivation service refuses to overwrite a dict with
    ``auto_filled=False`` to preserve manual overrides.
    """

    serving_size_g: int = 0
    servings_per_container: int = 1

    energy_kcal: float | None = None
    carbohydrates_g: float | None = None
    sugars_g: float | None = None
    proteins_g: float | None = None
    total_fat_g: float | None = None
    saturated_fat_g: float | None = None
    trans_fat_g: float | None = None
    fiber_g: float | None = None
    sodium_mg: float | None = None

    auto_filled: bool = False

    # ── Construction / serialization ──────────────────────────────

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> NutritionFacts | None:
        """Rehydrate from a JSON-ish dict. Empty/None → ``None``."""
        if not data:
            return None
        known = {f.name for f in fields(cls)}
        clean: dict[str, Any] = {}
        for key, value in data.items():
            if key not in known:
                continue
            if value is None:
                clean[key] = None
                continue
            if key in ("serving_size_g", "servings_per_container"):
                clean[key] = int(value)
            elif key == "auto_filled":
                clean[key] = bool(value)
            else:
                clean[key] = float(value)
        return cls(**clean)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict suitable for ``JSONField``."""
        return asdict(self)

    # ── Derived values ────────────────────────────────────────────

    def percent_daily_value(self, field_name: str) -> int | None:
        """Return %VD for ``field_name`` rounded to nearest int.

        Returns ``None`` when the nutrient has no DRV defined by
        ANVISA or when the value is missing/zero.
        """
        value = getattr(self, field_name, None)
        if value is None or value == 0:
            return None
        drv = DRV_2000_KCAL.get(field_name)
        if drv is None or drv == 0:
            return None
        return round((float(value) / drv) * 100)

    @property
    def has_any_nutrient(self) -> bool:
        """True when at least one nutrient (other than serving size) is set."""
        nutrients = (
            "energy_kcal",
            "carbohydrates_g",
            "sugars_g",
            "proteins_g",
            "total_fat_g",
            "saturated_fat_g",
            "trans_fat_g",
            "fiber_g",
            "sodium_mg",
        )
        return any(getattr(self, n) is not None for n in nutrients)


# Names of numeric nutrient fields (stable for admin form / projection rendering).
NUTRIENT_FIELDS: tuple[str, ...] = (
    "energy_kcal",
    "carbohydrates_g",
    "sugars_g",
    "proteins_g",
    "total_fat_g",
    "saturated_fat_g",
    "trans_fat_g",
    "fiber_g",
    "sodium_mg",
)

# Display labels for the admin form and the PDP.
NUTRIENT_LABELS_PT: dict[str, str] = {
    "serving_size_g": "Porção (g)",
    "servings_per_container": "Porções por embalagem",
    "energy_kcal": "Valor energético (kcal)",
    "carbohydrates_g": "Carboidratos (g)",
    "sugars_g": "Açúcares (g)",
    "proteins_g": "Proteínas (g)",
    "total_fat_g": "Gorduras totais (g)",
    "saturated_fat_g": "Gorduras saturadas (g)",
    "trans_fat_g": "Gorduras trans (g)",
    "fiber_g": "Fibra alimentar (g)",
    "sodium_mg": "Sódio (mg)",
}
