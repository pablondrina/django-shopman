from __future__ import annotations

_DEFAULT_DDD_FALLBACK = "43"


def get_default_ddd() -> str:
    """Get default DDD from Shop, with fallback."""
    try:
        from shop.models import Shop

        shop = Shop.load()
        return shop.default_ddd if shop else _DEFAULT_DDD_FALLBACK
    except Exception:
        return _DEFAULT_DDD_FALLBACK


# Kept for backwards compat — views should prefer get_default_ddd()
DEFAULT_DDD = _DEFAULT_DDD_FALLBACK

# Check if auth is available for inline auth
try:
    from django.apps import apps as _apps

    _apps.get_app_config("shopman_auth")
    HAS_AUTH = True
except LookupError:
    HAS_AUTH = False


# Check if stocking availability API is available
try:
    from shopman.stocking.api.views import _availability_for_sku, _get_safety_margin  # noqa: F401

    HAS_STOCKING = True
except ImportError:
    HAS_STOCKING = False


LISTING_REFS = ("balcao", "whatsapp")
STOREFRONT_CHANNEL_REF = "web"
