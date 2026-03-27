from __future__ import annotations

from django.http import HttpRequest


def shop(request: HttpRequest) -> dict:
    """Inject Shop singleton, shop status, and customer name into all templates."""
    from channels.web.views._helpers import _format_opening_hours, _shop_status

    from .models import Shop

    # Customer display name for nav
    customer_info = getattr(request, "customer", None)
    customer_name = customer_info.name if customer_info else ""
    # Use first_name for greeting if available
    if customer_name and " " in customer_name:
        customer_name = customer_name.split()[0]

    return {
        "storefront": Shop.load() or Shop(name="Shopman"),
        "shop_status": _shop_status(),
        "opening_hours_display": _format_opening_hours(),
        "customer_name": customer_name,
    }
