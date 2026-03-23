from __future__ import annotations

from django.apps import AppConfig


class WebChannelConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "channels.web"
    label = "web_channel"
    verbose_name = "Canal Web (E-commerce)"
