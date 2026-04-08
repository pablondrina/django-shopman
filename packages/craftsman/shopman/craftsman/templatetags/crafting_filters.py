from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def weight(value):
    """Format a numeric value as weight with 2 decimal places."""
    if value is None:
        return "0,00"
    try:
        d = Decimal(str(value)).quantize(Decimal("0.01"))
        return f"{d:,}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError, ArithmeticError):
        return str(value)
