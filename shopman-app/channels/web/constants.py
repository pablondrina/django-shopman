from __future__ import annotations

_DEFAULT_DDD_FALLBACK = "43"


def get_default_ddd() -> str:
    """Get default DDD from StorefrontConfig, with fallback."""
    try:
        from .models import StorefrontConfig

        return StorefrontConfig.load().default_ddd or _DEFAULT_DDD_FALLBACK
    except Exception:
        return _DEFAULT_DDD_FALLBACK


# Kept for backwards compat — views should prefer get_default_ddd()
DEFAULT_DDD = _DEFAULT_DDD_FALLBACK

# Check if doorman is available for inline auth
try:
    from django.apps import apps as _apps

    _apps.get_app_config("shopman.gating")
    HAS_DOORMAN = True
except LookupError:
    HAS_DOORMAN = False

# Check if stockman availability API is available
try:
    from shopman.stocking.api.views import _availability_for_sku, _get_safety_margin  # noqa: F401

    HAS_STOCKMAN = True
except ImportError:
    HAS_STOCKMAN = False

LISTING_CODES = ("balcao", "whatsapp")
STOREFRONT_CHANNEL_REF = "web"
