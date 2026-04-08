"""Stocking Alerts dispatch app configuration."""

from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class StockingAlertsConfig(AppConfig):
    """Signal-driven stock alert dispatch."""

    name = "shopman.stockman.contrib.alerts"
    label = "stocking_alerts"
    verbose_name = _("Alertas de Estoque")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from shopman.stockman.contrib.alerts import handlers  # noqa: F401
