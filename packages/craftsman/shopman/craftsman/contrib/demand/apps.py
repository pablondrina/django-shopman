"""Craftsman Demand backend app configuration."""

from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CraftsmanDemandConfig(AppConfig):
    """Demand backend powered by Orderman order history."""

    name = "shopman.craftsman.contrib.demand"
    label = "craftsman_demand"
    verbose_name = _("Backend de Demanda")
    default_auto_field = "django.db.models.BigAutoField"
