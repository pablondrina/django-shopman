from __future__ import annotations

from django.conf import settings
from django.utils.module_loading import import_string


ORDERMAN_DEFAULTS = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "ADMIN_PERMISSION_CLASSES": ["rest_framework.permissions.IsAdminUser"],
}


def get_orderman_setting(key: str):
    """Retrieve an Orderman setting, falling back to ORDERMAN_DEFAULTS."""
    user_settings = getattr(settings, "ORDERMAN", {})
    value = user_settings.get(key, ORDERMAN_DEFAULTS.get(key))
    if isinstance(value, list) and value and isinstance(value[0], str):
        return [import_string(cls) for cls in value]
    return value
