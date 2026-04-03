"""
Shopman adapters — swappable backends resolved via settings.

Resolution order for get_adapter():
  1. Channel override (channel.config["<type>_adapter"])
  2. Global settings (SHOPMAN_<TYPE>_ADAPTERS[method])
  3. Default adapter for the type

Usage:
    from shopman.adapters import get_adapter

    adapter = get_adapter("payment", method="pix")
    adapter = get_adapter("notification", channel=channel)
    adapter = get_adapter("stock")
    adapter = get_adapter("fiscal")
"""

from importlib import import_module

from django.conf import settings

# Mapping from adapter type → settings key
_SETTINGS_MAP = {
    "payment": "SHOPMAN_PAYMENT_ADAPTERS",
    "notification": "SHOPMAN_NOTIFICATION_ADAPTERS",
    "stock": "SHOPMAN_STOCK_ADAPTER",
    "fiscal": "SHOPMAN_FISCAL_ADAPTER",
}

# Defaults when settings are absent
_DEFAULTS = {
    "payment": {
        "pix": "shopman.adapters.payment_mock",
        "card": "shopman.adapters.payment_mock",
        "counter": None,
        "external": None,
    },
    "notification": {
        "console": "shopman.adapters.notification_console",
    },
    "stock": "shopman.adapters.stock_internal",
    "fiscal": None,
}


def _resolve_module(dotted_path):
    """Import and return a module from a dotted path string."""
    if dotted_path is None:
        return None
    return import_module(dotted_path)


def get_adapter(adapter_type, method=None, channel=None):
    """
    Resolve an adapter module by type, optional method, and optional channel.

    Resolution order:
      1. Channel override — channel.config.get("<type>_adapter")
      2. Global settings — SHOPMAN_<TYPE>_ADAPTERS (dict for multi-method, string for single)
      3. Built-in default

    Returns the imported module, or None if the adapter is explicitly disabled.
    """
    # 1. Channel override
    if channel is not None:
        config = getattr(channel, "config", None) or {}
        override = config.get(f"{adapter_type}_adapter")
        if override:
            return _resolve_module(override)

    # 2. Global settings
    settings_key = _SETTINGS_MAP.get(adapter_type)
    setting_value = getattr(settings, settings_key, None) if settings_key else None

    if setting_value is not None:
        if isinstance(setting_value, dict):
            # Multi-method adapter (payment, notification)
            if method and method in setting_value:
                return _resolve_module(setting_value[method])
            # If no method specified, return first non-None adapter
            for path in setting_value.values():
                if path is not None:
                    return _resolve_module(path)
            return None
        else:
            # Single adapter (stock, fiscal)
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
