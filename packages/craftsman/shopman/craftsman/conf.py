"""
Craftsman Settings (vNext).

Supports two formats (dict takes priority):

    # Option 1: Dict
    CRAFTSMAN = {
        "INVENTORY_BACKEND": "shopman.craftsman.adapters.stocking.StockingBackend",
    }

    # Option 2: Flat
    CRAFTSMAN_INVENTORY_BACKEND = "shopman.craftsman.adapters.stocking.StockingBackend"

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
    1. CRAFTSMAN dict (e.g. CRAFTSMAN = {"INVENTORY_BACKEND": "..."})
    2. Flat setting (e.g. CRAFTSMAN_INVENTORY_BACKEND = "...")
    3. DEFAULTS
    """
    crafting_dict = getattr(settings, "CRAFTSMAN", {})
    if name in crafting_dict:
        return crafting_dict[name]

    flat_value = getattr(settings, f"CRAFTSMAN_{name}", _sentinel)
    if flat_value is not _sentinel:
        return flat_value

    if default is not _sentinel:
        return default

    return DEFAULTS.get(name)
