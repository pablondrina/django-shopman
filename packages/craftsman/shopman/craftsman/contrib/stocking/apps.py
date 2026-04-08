"""Crafting Stocking integration app configuration."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CraftingStockingConfig(AppConfig):
    """Registers Stocking signal handlers for Crafting."""

    name = "shopman.craftsman.contrib.stocking"
    label = "crafting_stocking"
    verbose_name = _("Integração Stocking")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from shopman.craftsman.contrib.stocking import handlers  # noqa: F401
