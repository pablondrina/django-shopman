"""Django AppConfig for the Shopman backstage (operator-facing surfaces)."""

from __future__ import annotations

from django.apps import AppConfig


class BackstageConfig(AppConfig):
    name = "shopman.backstage"
    label = "backstage"
    verbose_name = "Backstage"
    default_auto_field = "django.db.models.BigAutoField"
