"""Identifiers app config."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class IdentifiersConfig(AppConfig):
    name = "shopman.guestman.contrib.identifiers"
    label = "customers_identifiers"
    verbose_name = _("Identificadores")
