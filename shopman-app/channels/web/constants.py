from __future__ import annotations

DEFAULT_DDD = "43"  # Londrina — Nelson Boulangerie

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
