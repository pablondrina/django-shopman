"""Crafting Stockman integration app configuration."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CraftingStockmanConfig(AppConfig):
    """Registers Stockman signal handlers for Crafting."""

    name = "shopman.crafting.contrib.stockman"
    label = "crafting_stockman"
    verbose_name = _("Integração Stockman")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from shopman.crafting.contrib.stockman import handlers  # noqa: F401
