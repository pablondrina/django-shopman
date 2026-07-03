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
signal handlers in contrib.stockman.

Default None here (standalone Craftsman = guardrails dormant). The orchestrator
wires it to shopman.shop.adapters.inventory.InventoryAvailabilityBackend (Buyman
WP-B5b), and the seed gives ingredients real Stockman stock so the guardrails
have something to check. With a real backend, adjust()/finish() validate that the
recipe's ingredients are on hand (insufficient → INSUFFICIENT_MATERIALS).
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
    # Dotted path to a callable returning [(value, label), ...] for the
    # Recipe.meta["production_lifecycle"] admin field. The orchestrator that
    # dispatches production lifecycles provides it; unset = field hidden
    # (Craftsman itself has no lifecycle concept).
    "PRODUCTION_LIFECYCLE_PROVIDER": None,
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
