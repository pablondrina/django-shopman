"""
CostBackend protocol.

Allows external apps (e.g. Craftsman) to provide production cost
for a product without Offering importing them.

Usage:
    # In settings.py
    OFFERING = {
        "COST_BACKEND": "craftsman.adapters.offering.CraftsmanCostBackend",
    }

    # Craftsman implements the adapter:
    class CraftsmanCostBackend:
        def get_cost(self, sku: str) -> int | None:
            recipe = Recipe.objects.filter(output_sku=sku).first()
            return recipe.total_cost_q if recipe else None
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class CostBackend(Protocol):
    """
    Interface for retrieving production cost of a product.

    Implemented by apps that own cost data (e.g. Craftsman).
    Offering reads cost via this Protocol for margin calculations.
    """

    def get_cost(self, sku: str) -> int | None:
        """
        Return production cost in centavos for the given SKU.

        Args:
            sku: Product SKU code

        Returns:
            Cost in centavos (int) or None if cost is unknown.
        """
        ...
