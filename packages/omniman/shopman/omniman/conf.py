from __future__ import annotations

from django.conf import settings
from django.utils.module_loading import import_string


OMNIMAN_DEFAULTS = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "ADMIN_PERMISSION_CLASSES": ["rest_framework.permissions.IsAdminUser"],
}


def get_omniman_setting(key: str):
    """Retrieve an Omniman setting, falling back to OMNIMAN_DEFAULTS."""
    user_settings = getattr(settings, "OMNIMAN", {})
    value = user_settings.get(key, OMNIMAN_DEFAULTS.get(key))
    if isinstance(value, list) and value and isinstance(value[0], str):
        return [import_string(cls) for cls in value]
    return value
