"""
Craftsman Settings (vNext).

Supports two formats (dict takes priority):

    # Option 1: Dict
    CRAFTSMAN = {
        "DEMAND_BACKEND": "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend",
    }

    # Option 2: Flat
    CRAFTSMAN_DEMAND_BACKEND = "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend"

All settings have sensible defaults — zero configuration required.

INVENTORY_BACKEND is a read-only seam for ingredient-availability guardrails
(over-plan on adjust, missing-on-finish, shortage status on suggestions). Stock
ledger writes are NOT done through it — they flow through the production_changed
signal handlers in contrib.stockman. Default None: the guardrails stay dormant.

⚠️  DO NOT wire INVENTORY_BACKEND until ingredient stock is first-class (Buyman
    WP-B5, docs/plans/BUYMAN-PROCUREMENT-PLAN.md). Today ingredients carry no
    Stockman quants, so any real available() returns 0 and would BLOCK adjust()
    and finish() across the board. Activating these guardrails is a tracked
    Buyman deliverable, not a drop-in setting.
"""

from decimal import Decimal

from django.conf import settings

# ── Defaults ──

DEFAULTS = {
    # "graceful" (default): backend failures log warning and continue.
    # "strict": backend failures abort the operation with CraftError.
    "MODE": "graceful",
    "INVENTORY_BACKEND": None,
    "CATALOG_BACKEND": None,
    "DEMAND_BACKEND": None,
    "SAFETY_STOCK_PERCENT": Decimal("0.20"),
    "HISTORICAL_DAYS": 28,
    "SAME_WEEKDAY_ONLY": True,
    "FORMULA_FACTOR_PROVIDERS": [],
    "FORMULA_ROUNDING_MULTIPLE": None,
    "FORMULA_CAPACITY_PROVIDER": None,
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
