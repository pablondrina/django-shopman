"""
Formula planning vertical for bakery-style production.

This contrib deliberately does not define a FormulaPlan model. Suggestions are
ephemeral read models; accepted lines are materialized as Craftsman WorkOrders.
"""

from shopman.craftsman.contrib.formula.service import (
    FormulaAvailabilityError,
    FormulaSuggestionLine,
    accept_suggestion,
    suggest,
)

__all__ = [
    "FormulaAvailabilityError",
    "FormulaSuggestionLine",
    "accept_suggestion",
    "suggest",
]
