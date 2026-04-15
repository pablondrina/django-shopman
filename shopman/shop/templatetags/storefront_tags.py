from __future__ import annotations

import json

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

# Material Symbols Rounded — ligature names (generic SKU hint → icon)
_PRODUCT_SYMBOL_MAP = {
    "BEB": "local_drink",
    "DRINK": "local_drink",
    "CAFE": "local_cafe",
    "COFFEE": "local_cafe",
    "COMBO": "inventory_2",
    "KIT": "inventory_2",
    "MEAL": "lunch_dining",
    "FOOD": "restaurant",
}
_DEFAULT_PRODUCT_SYMBOL = "restaurant_menu"


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
def get_item(mapping, key):
    """Lookup em dict para templates: {{ mydict|get_item:key }}"""
    if mapping is None:
        return None
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def product_icon(sku: str, size_class: str = "icon-lg") -> str:
    """Ícone Material Symbols (ligature) por prefixo do SKU. size_class = classe CSS (ex.: icon-product-hero)."""
    sku_upper = (sku or "").upper()
    name = _DEFAULT_PRODUCT_SYMBOL
    for prefix, sym in _PRODUCT_SYMBOL_MAP.items():
        if prefix in sku_upper:
            name = sym
            break
    sc = (size_class or "icon-lg").strip() or "icon-lg"
    return mark_safe(f'<span class="material-symbols-rounded {sc}" aria-hidden="true">{name}</span>')


@register.filter
def format_money(value_q) -> str:
    """Format centavos integer to BRL display: 1500 → R$\u00a015,00"""
    try:
        cents = int(value_q)
    except (TypeError, ValueError):
        return "R$\u00a00,00"
    reais = cents / 100
    formatted = f"{reais:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$\u00a0{formatted}"


# ── Product Image Tag ─────────────────────────────────────────────────

_SIZES = {
    "thumb": 200,
    "card": 400,
    "detail": 800,
}

_PLACEHOLDER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" fill="none">'
    '<rect width="400" height="400" rx="8" fill="rgb(var(--muted))"/>'
    '<path d="M170 220c0-16.569 13.431-30 30-30s30 13.431 30 30'
    'c0 11.046-5.97 20.69-14.862 25.882L230 280H170l14.862-34.118'
    'C175.97 240.69 170 231.046 170 220z" fill="rgb(var(--border))"/>'
    '<circle cx="200" cy="170" r="18" fill="rgb(var(--border))"/>'
    "</svg>"
)


@register.simple_tag
def product_image(product, size="card", css_class=""):
    """Render a product image with srcset, lazy loading, and placeholder fallback.

    Usage: {% product_image product size="card" css_class="rounded-lg" %}

    Sizes: thumb (200px), card (400px), detail (800px).
    Falls back to a branded SVG placeholder if no image is set.
    """
    width = _SIZES.get(size, 400)
    alt = escape(getattr(product, "name", "Produto"))
    css = escape(css_class)

    # Check if product has an image
    image = getattr(product, "image", None)
    if image and hasattr(image, "url") and image.name:
        url = escape(image.url)
        # Build srcset if multiple sizes available
        srcset_parts = []
        for _sz_name, sz_width in sorted(_SIZES.items(), key=lambda x: x[1]):
            srcset_parts.append(f"{url} {sz_width}w")
        srcset = ", ".join(srcset_parts)

        return mark_safe(
            f'<img src="{url}" srcset="{srcset}" '
            f'sizes="(max-width: 640px) 100vw, {width}px" '
            f'width="{width}" height="{width}" '
            f'loading="lazy" decoding="async" '
            f'alt="{alt}" class="{css} object-cover">'
        )

    # Placeholder: inline SVG data URI
    placeholder_b64 = (
        "data:image/svg+xml,"
        + _PLACEHOLDER_SVG.replace("#", "%23").replace("<", "%3C").replace(">", "%3E").replace('"', "'")
    )

    return mark_safe(
        f'<img src="{placeholder_b64}" '
        f'width="{width}" height="{width}" '
        f'alt="{alt}" class="{css} object-cover" '
        f'role="img">'
    )


@register.simple_tag(takes_context=True)
def json_ld_product(context, product, price_q=None, badge=None):
    """Render JSON-LD Product schema for SEO.

    Usage: {% json_ld_product product price_q=price_q badge=badge %}
    """
    shop = context.get("shop")
    request = context.get("request")

    data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": product.name,
        "sku": product.sku,
    }

    # Description
    desc = getattr(product, "short_description", "") or getattr(product, "description", "")
    if desc:
        data["description"] = desc

    # Image
    image = getattr(product, "image", None)
    if image and hasattr(image, "url") and image.name:
        if request:
            data["image"] = request.build_absolute_uri(image.url)
        else:
            data["image"] = image.url

    # Brand
    if shop:
        data["brand"] = {"@type": "Brand", "name": getattr(shop, "name", "")}

    # Offer
    if price_q is not None:
        offer = {
            "@type": "Offer",
            "priceCurrency": "BRL",
            "price": f"{price_q / 100:.2f}",
        }
        # Availability
        if badge:
            css = badge.get("css_class", "") if isinstance(badge, dict) else ""
            if css in ("badge-available", "badge-d1", "badge-preparing"):
                offer["availability"] = "https://schema.org/InStock"
            elif css == "badge-sold-out":
                offer["availability"] = "https://schema.org/OutOfStock"
            else:
                offer["availability"] = "https://schema.org/LimitedAvailability"
        data["offers"] = offer

    # Escape `</` to prevent `</script>` injection inside JSON payload.
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return mark_safe(f'<script type="application/ld+json">{payload}</script>')
