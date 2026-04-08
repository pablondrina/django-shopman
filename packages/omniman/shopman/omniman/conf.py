from __future__ import annotations

from django.conf import settings
from django.utils.module_loading import import_string


ORDERING_DEFAULTS = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "ADMIN_PERMISSION_CLASSES": ["rest_framework.permissions.IsAdminUser"],
}


def get_ordering_setting(key: str):
    """Retrieve an Ordering setting, falling back to ORDERING_DEFAULTS."""
    user_settings = getattr(settings, "ORDERING", {})
    value = user_settings.get(key, ORDERING_DEFAULTS.get(key))
    if isinstance(value, list) and value and isinstance(value[0], str):
        return [import_string(cls) for cls in value]
    return value
