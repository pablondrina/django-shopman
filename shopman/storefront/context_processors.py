"""Shopman context processors — inject shop and customer data into templates."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest

from .models import Shop


def shop(request: HttpRequest) -> dict:
    """Inject Shop singleton and customer name into all templates."""
    # Customer display name for nav
    customer_info = getattr(request, "customer", None)
    customer_name = customer_info.name if customer_info else ""
    customer_phone = (customer_info.phone if customer_info else "") or ""
    customer_email = (customer_info.email if customer_info else "") or ""
    # Use first_name for greeting if available
    if customer_name and " " in customer_name:
        customer_name = customer_name.split()[0]

    shop_instance = Shop.load() or Shop(name="Shopman")

    # Location data for Google Places proximity bias
    shop_location = {}
    if shop_instance.latitude and shop_instance.longitude:
        shop_location = {
            "lat": float(shop_instance.latitude),
            "lng": float(shop_instance.longitude),
        }
    elif shop_instance.city:
        shop_location = {
            "city": shop_instance.city,
            "state": shop_instance.state_code,
        }

    try:
        from .web.views._helpers import _format_opening_hours, _shop_status

        shop_status = _shop_status()
        opening_hours_display = _format_opening_hours()
    except Exception:
        shop_status = {"is_open": True, "message": None, "opens_at": None, "closes_at": None}
        opening_hours_display = []

    # Resolve handle_label from the effective channel config
    try:
        from shopman.shop.config import ChannelConfig
        from shopman.shop.models import Channel
        from shopman.storefront.constants import STOREFRONT_CHANNEL_REF

        _channel = Channel.objects.get(ref=STOREFRONT_CHANNEL_REF)
        _cfg = ChannelConfig.for_channel(_channel)
        handle_label = _cfg.handle_label
        handle_placeholder = _cfg.handle_placeholder
    except Exception:
        handle_label = "Identificador"
        handle_placeholder = ""

    return {
        "storefront": shop_instance,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "customer_email": customer_email,
        "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY,
        "stripe_publishable_key": getattr(settings, "STRIPE_PUBLISHABLE_KEY", ""),
        "shop_location": shop_location,
        "shop_status": shop_status,
        "opening_hours_display": opening_hours_display,
        "handle_label": handle_label,
        "handle_placeholder": handle_placeholder,
        "storefront_channel_ref": getattr(
            settings, "SHOPMAN_STOREFRONT_CHANNEL_REF", "web"
        ),
        "pos_channel_ref": getattr(settings, "SHOPMAN_POS_CHANNEL_REF", "balcao"),
    }


def omotenashi(request: HttpRequest) -> dict:
    """Inject OmotenashiContext (QUANDO + QUEM) into every template.

    Consumed by the `{% omotenashi %}` tag and by storefront partials that
    currently duplicate time-of-day logic in Alpine.
    """
    from shopman.storefront.omotenashi import OmotenashiContext

    try:
        ctx = OmotenashiContext.from_request(request)
    except Exception:
        ctx = OmotenashiContext.from_request(None)
    return {"omotenashi_ctx": ctx}


def cart_count(request: HttpRequest) -> dict:
    """Expose cart item count and subtotal from Orderman session to all templates."""
    from shopman.storefront.cart import CartService

    cart = CartService.get_cart(request)
    return {
        "cart_count": cart["count"],
        "cart_subtotal_display": cart["subtotal_display"],
    }
