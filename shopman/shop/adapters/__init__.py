"""
Shopman adapters — swappable backends resolved at runtime.

Resolution order for get_adapter():
  1. Shop.integrations (DB — Admin-configurável, sobreescreve tudo)
  2. Settings (SHOPMAN_<TYPE>_ADAPTERS — deploy-level config)
  3. Built-in defaults

Usage:
    from shopman.shop.adapters import get_adapter

    adapter = get_adapter("payment", method="pix")
    adapter = get_adapter("notification")
    adapter = get_adapter("stock")
    adapter = get_adapter("fiscal")
"""

import logging
from importlib import import_module

from django.conf import settings

logger = logging.getLogger(__name__)

# Mapping from adapter type → settings key
_SETTINGS_MAP = {
    "payment": "SHOPMAN_PAYMENT_ADAPTERS",
    "notification": "SHOPMAN_NOTIFICATION_ADAPTERS",
    "stock": "SHOPMAN_STOCK_ADAPTER",
    "fiscal": "SHOPMAN_FISCAL_ADAPTER",
    "catalog": "SHOPMAN_CATALOG_ADAPTER",
    "production": "SHOPMAN_PRODUCTION_ADAPTER",
    "customer": "SHOPMAN_CUSTOMER_ADAPTER",
    "promotion": "SHOPMAN_PROMOTION_ADAPTER",
}

# Defaults when settings are absent
_DEFAULTS = {
    "payment": {
        "pix": "shopman.shop.adapters.payment_mock",
        "card": "shopman.shop.adapters.payment_mock",
        "cash": None,
        "external": None,
    },
    "notification": {
        "console": "shopman.shop.adapters.notification_console",
    },
    "stock": "shopman.shop.adapters.stock",
    "fiscal": None,
    "catalog": "shopman.shop.adapters.catalog",
    "production": "shopman.shop.adapters.production",
    "customer": "shopman.shop.adapters.customer",
    "promotion": "shopman.shop.adapters.promotion",
}


def _resolve_module(dotted_path):
    """Import and return a module from a dotted path string."""
    if dotted_path is None:
        return None
    return import_module(dotted_path)


def _from_shop_integrations(adapter_type: str, method=None):
    """Read adapter config from Shop.integrations (Admin-configurable, highest priority)."""
    try:
        from shopman.shop.models import Shop
        shop = Shop.load()
        if not shop or not shop.integrations:
            return None, False
        integrations = shop.integrations
        value = integrations.get(adapter_type)
        if value is None:
            return None, False
        # Found a value — now resolve it
        if isinstance(value, dict):
            if method and method in value:
                return _resolve_module(value[method]), True
            # "default" key as fallback
            if "default" in value:
                return _resolve_module(value["default"]), True
            for path in value.values():
                if path is not None:
                    return _resolve_module(path), True
            return None, True
        else:
            return _resolve_module(value), True
    except Exception:
        logger.debug("_from_shop_integrations: DB lookup failed for %s", adapter_type, exc_info=True)
        return None, False


def get_adapter(adapter_type, method=None, channel=None):
    """
    Resolve an adapter module by type and optional method.

    Resolution order:
      1. Shop.integrations (DB — Admin-configurável)
      2. Settings (SHOPMAN_<TYPE>_ADAPTERS)
      3. Built-in defaults

    Returns the imported module, or None if the adapter is explicitly disabled.
    """
    # 1. Shop.integrations (Admin-configurable, overrides everything)
    adapter, found = _from_shop_integrations(adapter_type, method)
    if found:
        return adapter

    # 2. Settings
    settings_key = _SETTINGS_MAP.get(adapter_type)
    setting_value = getattr(settings, settings_key, None) if settings_key else None

    if setting_value is not None:
        if isinstance(setting_value, dict):
            if method and method in setting_value:
                return _resolve_module(setting_value[method])
            for path in setting_value.values():
                if path is not None:
                    return _resolve_module(path)
            return None
        else:
            return _resolve_module(setting_value)

    # 3. Defaults
    default = _DEFAULTS.get(adapter_type)
    if default is None:
        return None
    if isinstance(default, dict):
        if method and method in default:
            return _resolve_module(default[method])
        for path in default.values():
            if path is not None:
                return _resolve_module(path)
        return None
    return _resolve_module(default)
