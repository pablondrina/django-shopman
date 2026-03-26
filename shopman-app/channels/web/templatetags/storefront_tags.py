from __future__ import annotations

from django import template

register = template.Library()

_EMOJI_MAP = {
    "PAO": "\U0001f35e",
    "BAGUETE": "\U0001f956",
    "CROISSANT": "\U0001f950",
    "PAIN": "\U0001f950",
    "BRIOCHE": "\U0001f9c1",
    "FOCACCIA": "\U0001fad3",
    "CIABATTA": "\U0001f35e",
    "CAFE": "\u2615",
    "COMBO": "\U0001f9fa",
}


@register.filter
def format_phone(value: str) -> str:
    """Format E.164 phone for display: +5543999999999 → (43) 99999-9999"""
    if not value:
        return value
    digits = "".join(c for c in value if c.isdigit())
    # Brazilian mobile: 55 + DDD(2) + 9XXXX-XXXX (13 digits)
    if len(digits) == 13 and digits.startswith("55"):
        ddd = digits[2:4]
        num = digits[4:]
        return f"({ddd}) {num[:5]}-{num[5:]}"
    # Brazilian landline: 55 + DDD(2) + XXXX-XXXX (12 digits)
    if len(digits) == 12 and digits.startswith("55"):
        ddd = digits[2:4]
        num = digits[4:]
        return f"({ddd}) {num[:4]}-{num[4:]}"
    return value


@register.filter
def mask_ip(value: str) -> str:
    """Mask an IP address for privacy: 177.100.50.23 → 177.100.***"""
    if not value:
        return ""
    parts = value.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.***"
    return value[:8] + "***"


@register.filter
def product_emoji(sku: str) -> str:
    """Return an emoji based on the product SKU prefix."""
    sku_upper = (sku or "").upper()
    for prefix, emoji in _EMOJI_MAP.items():
        if prefix in sku_upper:
            return emoji
    return "\U0001f968"
