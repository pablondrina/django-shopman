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
def product_emoji(sku: str) -> str:
    """Return an emoji based on the product SKU prefix."""
    sku_upper = (sku or "").upper()
    for prefix, emoji in _EMOJI_MAP.items():
        if prefix in sku_upper:
            return emoji
    return "\U0001f968"
