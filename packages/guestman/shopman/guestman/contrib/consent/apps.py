"""Consent app config."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ConsentConfig(AppConfig):
    name = "shopman.guestman.contrib.consent"
    label = "customers_consent"
    verbose_name = _("Consentimento de Comunicação")
