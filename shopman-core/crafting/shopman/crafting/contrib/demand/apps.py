"""Crafting Demand backend app configuration."""

from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CraftingDemandConfig(AppConfig):
    """Demand backend powered by Omniman order history."""

    name = "shopman.crafting.contrib.demand"
    label = "crafting_demand"
    verbose_name = _("Backend de Demanda")
    default_auto_field = "django.db.models.BigAutoField"
