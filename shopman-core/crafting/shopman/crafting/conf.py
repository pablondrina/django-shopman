"""
Crafting Settings (vNext).

Supports two formats (dict takes priority):

    # Option 1: Dict
    CRAFTING = {
        "INVENTORY_BACKEND": "shopman.crafting.adapters.stocking.StockingBackend",
    }

    # Option 2: Flat
    CRAFTING_INVENTORY_BACKEND = "shopman.crafting.adapters.stocking.StockingBackend"

All settings have sensible defaults — zero configuration required.
"""

from decimal import Decimal

from django.conf import settings


# ── Defaults ──

DEFAULTS = {
    "INVENTORY_BACKEND": None,
    "CATALOG_BACKEND": None,
    "DEMAND_BACKEND": None,
    "SAFETY_STOCK_PERCENT": Decimal("0.20"),
    "HISTORICAL_DAYS": 28,
    "SAME_WEEKDAY_ONLY": True,
}


# ── Accessors ──

_sentinel = object()


def get_setting(name, default=_sentinel):
    """
    Get a crafting setting.

    Looks up in order:
    1. CRAFTING dict (e.g. CRAFTING = {"INVENTORY_BACKEND": "..."})
    2. Flat setting (e.g. CRAFTING_INVENTORY_BACKEND = "...")
    3. DEFAULTS
    """
    crafting_dict = getattr(settings, "CRAFTING", {})
    if name in crafting_dict:
        return crafting_dict[name]

    flat_value = getattr(settings, f"CRAFTING_{name}", _sentinel)
    if flat_value is not _sentinel:
        return flat_value

    if default is not _sentinel:
        return default

    return DEFAULTS.get(name)
