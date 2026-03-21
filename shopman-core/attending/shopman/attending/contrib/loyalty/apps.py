"""Loyalty app config."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LoyaltyConfig(AppConfig):
    name = "shopman.attending.contrib.loyalty"
    label = "attending_loyalty"
    verbose_name = _("Programa de Fidelidade")
