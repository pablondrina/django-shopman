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

    return {
        "storefront": shop_instance,
        "customer_name": customer_name,
        "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY,
        "shop_location": shop_location,
    }


def cart_count(request: HttpRequest) -> dict:
    """Expose cart item count and subtotal from Ordering session to all templates."""
    from shopman.web.cart import CartService

    cart = CartService.get_cart(request)
    return {
        "cart_count": cart["count"],
        "cart_subtotal_display": cart["subtotal_display"],
    }
