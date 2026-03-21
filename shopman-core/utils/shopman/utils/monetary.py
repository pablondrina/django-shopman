"""
Monetary utilities for the Shopman suite.

Convention: all monetary values are stored as integers in centavos (quantum, _q suffix).
base_price_q = 1050 means R$ 10.50.

This module provides the canonical rounding functions to ensure consistency
across all packages. All monetary arithmetic MUST use these functions.
"""

from decimal import ROUND_HALF_UP, Decimal

ONE = Decimal("1")


def monetary_mult(qty: Decimal, unit_price_q: int) -> int:
    """
    Multiply quantity by unit price (in centavos) with ROUND_HALF_UP.

    Args:
        qty: Quantity (Decimal)
        unit_price_q: Unit price in centavos (int)

    Returns:
        Total price in centavos (int), rounded half-up.

    Example:
        monetary_mult(Decimal("2.5"), 333)  # -> 833 (not 832)
    """
    return int((qty * unit_price_q).quantize(ONE, rounding=ROUND_HALF_UP))


def monetary_div(total_q: int, divisor: int) -> int:
    """
    Divide monetary value with ROUND_HALF_UP.

    Useful for averages, unit price back-calculation, etc.

    Args:
        total_q: Total in centavos (int)
        divisor: Divisor (int, must be > 0)

    Returns:
        Result in centavos (int), rounded half-up.

    Example:
        monetary_div(1000, 3)  # -> 333 (not 333.33)
    """
    if divisor <= 0:
        raise ValueError("divisor must be > 0")
    return int((Decimal(total_q) / Decimal(divisor)).quantize(ONE, rounding=ROUND_HALF_UP))


def format_money(value_q: int) -> str:
    """
    Format centavos as currency string with 2 decimal places.

    Args:
        value_q: Value in centavos (int)

    Returns:
        Formatted string with comma as decimal separator.

    Examples:
        format_money(1250)  # -> "12,50"
        format_money(0)     # -> "0,00"
        format_money(5)     # -> "0,05"
        format_money(-1250) # -> "-12,50"
    """
    d = Decimal(value_q) / 100
    return f"{d:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
