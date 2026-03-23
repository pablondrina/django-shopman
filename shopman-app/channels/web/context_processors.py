from __future__ import annotations

from django.http import HttpRequest


def cart_count(request: HttpRequest) -> dict:
    """Expose cart item count and subtotal from Omniman session to all templates."""
    from .cart import CartService

    cart = CartService.get_cart(request)
    return {
        "cart_count": cart["count"],
        "cart_subtotal_display": cart["subtotal_display"],
    }


def storefront_config(request: HttpRequest) -> dict:
    """Inject StorefrontConfig singleton into all templates as `storefront`."""
    from .models import StorefrontConfig

    return {"storefront": StorefrontConfig.load()}
