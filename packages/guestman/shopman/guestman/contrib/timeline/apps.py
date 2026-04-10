"""Timeline app config."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class TimelineConfig(AppConfig):
    name = "shopman.guestman.contrib.timeline"
    label = "customer_timeline"
    verbose_name = _("Timeline de Clientes")
