"""
Django Crafting — Headless Micro-MRP Framework (vNext).

5 models, 4 verbs, 3 states. Cabe na cabeca.

Usage:
    from shopman.craftsman import craft, CraftError

    wo = craft.plan(recipe, 100)
    craft.close(wo, produced=95)

    wo.produced      # 95
    wo.loss          # 5
    wo.yield_rate    # 0.95
    wo.events.all()  # [planned, closed]

Philosophy: SIREL (Simples, Robusto, Elegante)
"""

from shopman.craftsman.exceptions import CraftError, StaleRevision


def __getattr__(name):
    """Lazy import to avoid AppRegistryNotReady errors."""
    if name in ("craft", "Craft", "CraftService"):
        from shopman.craftsman.service import CraftService

        return CraftService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["craft", "CraftService", "Craft", "CraftError", "StaleRevision"]
__version__ = "0.2.2"
