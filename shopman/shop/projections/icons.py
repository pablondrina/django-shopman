"""Collection → Material Symbols ligature mapping.

Presentation layer only. Keys are matched by substring against the
collection ref, so ``cafes`` and ``cafe-gourmet`` both get ``local_cafe``.
Unknown refs fall back to ``restaurant_menu``.
"""

from __future__ import annotations

COLLECTION_ICONS: dict[str, str] = {
    "cafes": "local_cafe",
    "cafe": "local_cafe",
    "bebidas": "local_drink",
    "drinks": "local_drink",
    "combos": "inventory_2",
    "kits": "inventory_2",
    "ofertas": "sell",
    "promocoes": "sell",
    "snacks": "lunch_dining",
    "salgados": "lunch_dining",
    "lanches": "restaurant",
    "especiais": "star",
}

DEFAULT_ICON = "restaurant_menu"


def collection_icon(ref: str) -> str:
    """Return the Material Symbols ligature for a collection ref."""
    if not ref:
        return DEFAULT_ICON
    ref_lower = ref.lower()
    for key, icon in COLLECTION_ICONS.items():
        if key in ref_lower:
            return icon
    return DEFAULT_ICON
