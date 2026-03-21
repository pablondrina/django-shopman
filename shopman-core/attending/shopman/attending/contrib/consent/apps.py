"""Consent app config."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ConsentConfig(AppConfig):
    name = "shopman.attending.contrib.consent"
    label = "attending_consent"
    verbose_name = _("Consentimento de Comunicação")
