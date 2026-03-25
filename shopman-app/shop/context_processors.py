from __future__ import annotations

from django.http import HttpRequest


def shop(request: HttpRequest) -> dict:
    """Inject Shop singleton into all templates as `storefront` (backward-compatible)."""
    from .models import Shop

    return {"storefront": Shop.load() or Shop(name="Shopman")}
