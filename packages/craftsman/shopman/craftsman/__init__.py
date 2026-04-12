"""
Django Craftsman — Headless Micro-MRP Framework (vNext).

5 models, 5 verbs, 4 states. Cabe na cabeca.

Usage:
    from shopman.craftsman import craft, CraftError

    wo = craft.plan(recipe, 100)
    craft.start(wo, quantity=97)
    craft.finish(wo, finished=95)

    wo.started_qty   # 97
    wo.finished_qty  # 95
    wo.loss          # 2
    wo.yield_rate    # 0.9793...
    wo.events.all()  # [planned, started, finished]

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
__version__ = "0.3.0"
