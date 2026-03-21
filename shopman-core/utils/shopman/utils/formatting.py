"""Formatting utilities for the Shopman suite."""

from decimal import Decimal


def format_quantity(value: Decimal, decimal_places: int = 2) -> str:
    """
    Format a quantity value.

    Args:
        value: Decimal value to format.
        decimal_places: Number of decimal places (default: 2).

    Returns:
        Formatted string (e.g., "10.50"), or "-" if value is None.
    """
    if value is None:
        return "-"
    return f"{value:.{decimal_places}f}"
