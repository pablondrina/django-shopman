"""Preferences app config."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PreferencesConfig(AppConfig):
    name = "shopman.customers.contrib.preferences"
    label = "customers_preferences"
    verbose_name = _("Preferências")
