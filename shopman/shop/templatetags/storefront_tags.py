from __future__ import annotations

import json
import logging

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()
logger = logging.getLogger(__name__)

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


_AVAILABILITY_SCHEMA_MAP = {
    "available": "https://schema.org/InStock",
    "low_stock": "https://schema.org/LimitedAvailability",
    "planned_ok": "https://schema.org/PreOrder",
    "unavailable": "https://schema.org/OutOfStock",
}


@register.simple_tag(takes_context=True)
def json_ld_product(context, product, price_q=None, badge=None, availability=None):
    """Render JSON-LD Product schema for SEO.

    Usage: {% json_ld_product product price_q=price_q availability=product.availability %}

    Accepts either a badge dict (legacy, css_class based) or an Availability enum.
    """
    shop = context.get("shop") or context.get("storefront")
    request = context.get("request")

    data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": getattr(product, "name", ""),
        "sku": getattr(product, "sku", ""),
    }

    # Description (first non-empty: short, long, plain description)
    desc = (
        getattr(product, "short_description", "")
        or getattr(product, "long_description", "")
        or getattr(product, "description", "")
    )
    if desc:
        data["description"] = desc

    # Image — support both ImageField (model) and image_url (projection)
    image_url = None
    image = getattr(product, "image", None)
    if image and hasattr(image, "url") and getattr(image, "name", None):
        image_url = image.url
    elif getattr(product, "image_url", None):
        image_url = product.image_url
    if image_url:
        if request and image_url.startswith("/"):
            image_url = request.build_absolute_uri(image_url)
        data["image"] = image_url

    # Absolute URL to the PDP
    if request:
        try:
            data["url"] = request.build_absolute_uri()
        except Exception:
            logger.debug("json_ld_product: could not build product URL", exc_info=True)

    # Brand
    brand_name = getattr(shop, "brand_name", None) or getattr(shop, "name", "")
    if brand_name:
        data["brand"] = {"@type": "Brand", "name": brand_name}

    # Offer
    if price_q is not None:
        offer = {
            "@type": "Offer",
            "priceCurrency": "BRL",
            "price": f"{int(price_q) / 100:.2f}",
        }
        if request:
            try:
                offer["url"] = request.build_absolute_uri()
            except Exception:
                logger.debug("json_ld_product: could not build offer URL", exc_info=True)
        avail_key = None
        if availability is not None:
            avail_key = str(getattr(availability, "value", availability)).lower()
        elif badge:
            css = badge.get("css_class", "") if isinstance(badge, dict) else ""
            if css in ("badge-available", "badge-d1", "badge-preparing"):
                avail_key = "available"
            elif css == "badge-sold-out":
                avail_key = "unavailable"
            else:
                avail_key = "low_stock"
        if avail_key:
            offer["availability"] = _AVAILABILITY_SCHEMA_MAP.get(
                avail_key, "https://schema.org/LimitedAvailability",
            )
        data["offers"] = offer

    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return mark_safe(f'<script type="application/ld+json">{payload}</script>')


@register.simple_tag(takes_context=True)
def json_ld_bakery(context):
    """Render JSON-LD Bakery (LocalBusiness) schema for the homepage."""
    shop = context.get("storefront") or context.get("shop")
    request = context.get("request")
    if not shop:
        return ""

    data = {
        "@context": "https://schema.org",
        "@type": "Bakery",
        "name": getattr(shop, "brand_name", None) or getattr(shop, "name", ""),
    }
    desc = getattr(shop, "description", "") or getattr(shop, "tagline", "")
    if desc:
        data["description"] = desc

    if request:
        try:
            data["url"] = request.build_absolute_uri("/")
        except Exception:
            logger.debug("json_ld_bakery: could not build bakery URL", exc_info=True)

    logo = getattr(shop, "logo", None)
    if logo and hasattr(logo, "url") and getattr(logo, "name", None):
        img = logo.url
        if request and img.startswith("/"):
            img = request.build_absolute_uri(img)
        data["image"] = img
        data["logo"] = img

    address = {}
    if getattr(shop, "street", ""):
        address["streetAddress"] = shop.street
    if getattr(shop, "city", "") or getattr(shop, "default_city", ""):
        address["addressLocality"] = getattr(shop, "city", None) or shop.default_city
    if getattr(shop, "state_code", ""):
        address["addressRegion"] = shop.state_code
    if getattr(shop, "postal_code", ""):
        address["postalCode"] = shop.postal_code
    if address:
        address["@type"] = "PostalAddress"
        address["addressCountry"] = "BR"
        data["address"] = address

    if getattr(shop, "latitude", None) and getattr(shop, "longitude", None):
        data["geo"] = {
            "@type": "GeoCoordinates",
            "latitude": float(shop.latitude),
            "longitude": float(shop.longitude),
        }

    phone = getattr(shop, "phone", "") or getattr(shop, "whatsapp", "")
    if phone:
        data["telephone"] = phone

    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return mark_safe(f'<script type="application/ld+json">{payload}</script>')


@register.simple_tag
def json_ld_breadcrumb(items):
    """Render JSON-LD BreadcrumbList from [(name, url), ...]."""
    if not items:
        return ""
    data = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i + 1,
                "name": name,
                "item": url,
            }
            for i, (name, url) in enumerate(items)
        ],
    }
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return mark_safe(f'<script type="application/ld+json">{payload}</script>')


@register.simple_tag
def json_ld_faq(pairs):
    """Render JSON-LD FAQPage from [(question, answer), ...]."""
    if not pairs:
        return ""
    data = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a},
            }
            for q, a in pairs
        ],
    }
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return mark_safe(f'<script type="application/ld+json">{payload}</script>')
