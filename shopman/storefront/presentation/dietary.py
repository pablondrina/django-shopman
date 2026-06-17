"""Preference-aware dietary warnings (WP-5).

Omotenashi: inform, never hide silently. Given the customer's *active* food
preferences and a product's declared ``dietary_info``/``allergens``, surface a
short warning when there's a CLEAR conflict (a known trigger is present). We do
NOT warn on absence of a positive tag — incomplete data must not cry wolf.

Mapping is conservative and tunable. Source of the dietary attributes will move
to the Recipe/BOM (WP-7); this layer is agnostic to where they come from.
"""

from __future__ import annotations

# pref_key → {triggers: matched against allergens+dietary; safe: dietary tags
# that explicitly clear the restriction; label: pt-BR warning copy}
_PREF_CONFLICTS: dict[str, dict] = {
    "sem_gluten": {
        "triggers": {"glúten", "gluten", "trigo", "cevada", "centeio"},
        "safe": {"sem glúten", "sem gluten"},
        "label": "Contém glúten",
    },
    "sem_lactose": {
        "triggers": {"lactose", "leite", "laticínios"},
        "safe": {"sem lactose"},
        "label": "Contém lactose",
    },
    "vegano": {
        "triggers": {"leite", "ovo", "ovos", "mel", "manteiga", "lactose"},
        "safe": {"100% vegetal", "vegano"},
        "label": "Não é vegano",
    },
    "vegetariano": {
        "triggers": {"carne", "frango", "bacon", "gelatina", "peixe"},
        "safe": {"vegetariano", "vegano", "100% vegetal"},
        "label": "Contém ingrediente de origem animal",
    },
}


def dietary_warnings(
    active_prefs,
    *,
    dietary_info=(),
    allergens=(),
) -> tuple[str, ...]:
    """Warnings for a product given the customer's active food preferences.

    Empty when there is no logged-in preference or no clear conflict.
    """
    if not active_prefs:
        return ()

    diet = {str(d).strip().lower() for d in (dietary_info or ())}
    allg = {str(a).strip().lower() for a in (allergens or ())}
    haystack = diet | allg

    warnings: list[str] = []
    for pref in active_prefs:
        spec = _PREF_CONFLICTS.get(pref)
        if not spec:
            continue
        if spec.get("safe") and (spec["safe"] & diet):
            continue  # product explicitly declares it's compatible
        if spec["triggers"] & haystack:
            warnings.append(spec["label"])
    return tuple(warnings)
