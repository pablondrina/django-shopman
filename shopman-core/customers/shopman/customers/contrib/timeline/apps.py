"""Timeline app config."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class TimelineConfig(AppConfig):
    name = "shopman.customers.contrib.timeline"
    label = "customers_timeline"
    verbose_name = _("Timeline de Clientes")
