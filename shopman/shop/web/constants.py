from __future__ import annotations

from django.conf import settings
from shopman.stockman.services.availability import availability_for_sku  # noqa: F401

_DEFAULT_DDD_FALLBACK = "43"


def get_default_ddd() -> str:
    """Get default DDD from Shop, with fallback."""
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        return shop.default_ddd if shop else _DEFAULT_DDD_FALLBACK
    except Exception:
        return _DEFAULT_DDD_FALLBACK


# Check if auth is available for inline auth
try:
    from django.apps import apps as _apps

    _apps.get_app_config("doorman")
    HAS_AUTH = True
except LookupError:
    HAS_AUTH = False


HAS_STOCKMAN = True


# Override via SHOPMAN_STOREFRONT_CHANNEL_REF in your Django settings.
STOREFRONT_CHANNEL_REF: str = getattr(settings, "SHOPMAN_STOREFRONT_CHANNEL_REF", "web")

# Override via SHOPMAN_POS_CHANNEL_REF in your Django settings.
POS_CHANNEL_REF: str = getattr(settings, "SHOPMAN_POS_CHANNEL_REF", "balcao")
