from __future__ import annotations

from django.conf import settings


def get_webhook_setting(key: str):
    """Retrieve a webhook setting from SHOPMAN_WEBHOOK."""
    defaults = {
        "AUTH_TOKEN": None,
        "DEFAULT_CHANNEL": "whatsapp",
        "AUTH_HEADER": "X-Webhook-Token",
    }
    user_settings = getattr(settings, "SHOPMAN_WEBHOOK", {})
    return user_settings.get(key, defaults.get(key))
